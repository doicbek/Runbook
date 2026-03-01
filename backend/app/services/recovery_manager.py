"""Recovery and triage logic extracted from executor.py.

All functions have explicit parameters to avoid circular imports with executor.py.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable, Awaitable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Action, Task
from app.services.dag_scheduler import collect_downstream
from app.services.event_bus import event_bus
from app.services.recovery_planner import plan_recovery

logger = logging.getLogger(__name__)


def build_failure_history(failures: list[dict]) -> str:
    """Build a structured failure history string for injection into retry prompts."""
    lines = ["[FAILURE HISTORY — Previous attempts failed. Use this to avoid repeating mistakes.]\n"]
    for f in failures:
        lines.append(f"  Attempt {f['attempt']} (loop_type={f['loop_type']}):")
        lines.append(f"    Error: {f['error'][:400]}")
        if f.get("summary"):
            lines.append(f"    What was tried: {f['summary'][:300]}")
        lines.append("")
    lines.append("Do NOT repeat these approaches. Try a fundamentally different strategy.\n")
    return "\n".join(lines)


async def triage_failure(
    prompt: str,
    agent_type: str,
    error: str,
    attempt: int,
    prior_attempts: list[dict],
) -> str:
    """Ask a fast LLM whether to retry the same agent or spawn a recovery sub-action.

    Returns 'retry' or 'recovery'.
    """
    from app.services.llm_client import utility_completion

    prior_context = ""
    if prior_attempts:
        prior_lines = []
        for p in prior_attempts:
            prior_lines.append(
                f"  Attempt {p['attempt']} ({p['strategy']}): {p['error'][:200]}"
            )
        prior_context = "\nPrevious recovery attempts:\n" + "\n".join(prior_lines)

    system = (
        "You are a failure triage system. A task has failed and you must decide the "
        "best recovery strategy. Output ONLY one word: 'retry' or 'recovery'.\n\n"
        "Choose 'retry' when:\n"
        "- The error is transient (network timeout, rate limit, temporary unavailability)\n"
        "- The error is a minor prompt issue the same agent can fix with better context\n"
        "- The agent type is fundamentally correct for the task\n\n"
        "Choose 'recovery' when:\n"
        "- The error is deterministic (wrong API, missing capability, auth failure, bad approach)\n"
        "- The same error has already occurred in a prior retry attempt\n"
        "- The task needs a fundamentally different approach or decomposition\n"
        "- The agent type may be wrong for this task"
    )
    user = (
        f"Task: {prompt[:300]}\n"
        f"Agent type: {agent_type}\n"
        f"Error: {error[:500]}\n"
        f"Attempt number: {attempt}"
        f"{prior_context}"
    )

    try:
        raw = await utility_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=10,
            temperature=0.0,
        )
        decision = raw.strip().lower().rstrip(".")
        if decision in ("retry", "recovery"):
            return decision
        # If the LLM returned something unexpected, default based on attempt number
        return "retry" if attempt <= 1 else "recovery"
    except Exception as e:
        logger.warning(f"Triage LLM call failed: {e}, defaulting to retry")
        return "retry" if attempt <= 1 else "recovery"


async def spawn_recovery_sub_action(
    action_id: str,
    task_id: str,
    original_prompt: str,
    original_agent_type: str,
    error_message: str,
    attempt: int,
    max_attempts: int,
    prior_attempts: list[dict],
    dep_outputs: dict[str, str],
    log_callback: Callable[..., Awaitable[None]] | None,
) -> dict | None:
    """Spawn a recovery sub-action that plans and executes a fix for the error.

    Returns the sub-action agent's result dict on success, or None on failure.
    """
    from app.services.agents.sub_action_agent import SubActionAgent

    prior_context = ""
    if prior_attempts:
        prior_context = (
            "\n\nPrevious recovery attempts that also failed:\n"
            + "\n".join(
                f"  Attempt {p['attempt']} ({p['strategy']}): {p['error'][:200]}"
                for p in prior_attempts
            )
            + "\n\nDo NOT repeat any of these approaches. Try something fundamentally different."
        )

    recovery_prompt = (
        f"[ERROR RECOVERY — Attempt {attempt}]\n\n"
        f"A task in a workflow has failed and needs to be fixed.\n\n"
        f"Original task goal: {original_prompt}\n"
        f"Agent type that failed: {original_agent_type}\n"
        f"Error message:\n{error_message[:800]}\n"
        f"{prior_context}\n\n"
        f"Your mission: Achieve the SAME goal as the original task, but work around "
        f"the error. Plan multiple steps if needed:\n"
        f"1. Diagnose why the error occurred\n"
        f"2. Use an alternative approach, different data source, or different method\n"
        f"3. Produce the output that the original task was supposed to produce\n\n"
        f"The downstream workflow depends on your output — it must fulfill the same "
        f"contract as the original task."
    )

    if log_callback:
        await log_callback(
            "info",
            f"Spawning recovery sub-action (attempt {attempt}/{max_attempts}): "
            f"{error_message[:100]}",
        )

    await event_bus.publish(action_id, "task.recovering", {
        "task_id": task_id,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "error": error_message[:200],
    })

    try:
        agent = SubActionAgent()
        result = await agent.execute(
            task_id, recovery_prompt, dep_outputs, log_callback
        )
        return result
    except Exception as recovery_err:
        if log_callback:
            await log_callback(
                "error",
                f"Recovery sub-action attempt {attempt} failed: {recovery_err}",
            )
        return None


async def attempt_recovery(
    action_id: str,
    failed_tasks: list[Task],
    all_tasks: list[Task],
) -> bool:
    """
    For each genuinely-failed task (not just 'Dependency failed'), ask the
    recovery planner for replacement task(s), patch the DAG, and reset
    downstream tasks.  Returns True if at least one task was recovered.
    """
    from app.services.llm_client import get_default_model_for_agent

    async with async_session() as db:
        result = await db.execute(select(Action).where(Action.id == action_id))
        action = result.scalar_one()
        root_prompt = action.root_prompt

    task_map = {t.id: t for t in all_tasks}

    # Build reverse-dependency map
    dependents: dict[str, list[str]] = {}
    for t in all_tasks:
        for dep_id in t.dependencies:
            dependents.setdefault(dep_id, []).append(t.id)

    recovered_any = False

    for failed_task in failed_tasks:
        error_msg = failed_task.output_summary or "Unknown error"

        # Tasks that failed only because their dependency failed will be
        # reset automatically when we fix the root cause
        if error_msg == "Dependency failed":
            continue

        # Collect context from upstream completed tasks
        upstream_summaries: dict[str, str] = {}
        for dep_id in failed_task.dependencies:
            dep = task_map.get(dep_id)
            if dep and dep.status == "completed" and dep.output_summary:
                upstream_summaries[dep_id] = dep.output_summary[:400]

        # Ask the LLM for a replacement plan
        replacement_specs = await plan_recovery(
            root_prompt=root_prompt,
            failed_prompt=failed_task.prompt,
            failed_agent_type=failed_task.agent_type,
            error_message=error_msg,
            upstream_summaries=upstream_summaries,
        )

        if not replacement_specs:
            logger.warning(
                f"[Recovery] No replacement returned for task {failed_task.id} "
                f"({failed_task.agent_type})"
            )
            continue

        downstream_ids = collect_downstream(failed_task.id, dependents)

        async with async_session() as db:
            if len(replacement_specs) == 1:
                # ── single replacement: update the task in place ────────────
                spec = replacement_specs[0]
                res = await db.execute(select(Task).where(Task.id == failed_task.id))
                task = res.scalar_one()
                task.status = "pending"
                task.output_summary = None
                task.agent_type = spec.agent_type
                task.prompt = spec.prompt
                task.model = spec.model or get_default_model_for_agent(spec.agent_type)

                # Reset downstream tasks that only failed because of this one
                for ds_id in downstream_ids:
                    res = await db.execute(select(Task).where(Task.id == ds_id))
                    ds_task = res.scalar_one_or_none()
                    if ds_task and ds_task.output_summary == "Dependency failed":
                        ds_task.status = "pending"
                        ds_task.output_summary = None

            else:
                # ── multiple replacements: insert new tasks, rewire deps ────
                new_task_ids: list[str] = []
                for i, spec in enumerate(replacement_specs):
                    new_deps = (
                        failed_task.dependencies if i == 0 else [new_task_ids[-1]]
                    )
                    new_task = Task(
                        id=str(uuid.uuid4()),
                        action_id=action_id,
                        prompt=spec.prompt,
                        agent_type=spec.agent_type,
                        model=spec.model or get_default_model_for_agent(spec.agent_type),
                        dependencies=new_deps,
                        status="pending",
                    )
                    db.add(new_task)
                    await db.flush()
                    new_task_ids.append(new_task.id)

                last_new_id = new_task_ids[-1]

                # Rewire tasks that depended on the failed task
                for dep_task_id in dependents.get(failed_task.id, []):
                    res = await db.execute(select(Task).where(Task.id == dep_task_id))
                    dep_task = res.scalar_one_or_none()
                    if dep_task:
                        dep_task.dependencies = [
                            last_new_id if d == failed_task.id else d
                            for d in dep_task.dependencies
                        ]
                        if dep_task.output_summary == "Dependency failed":
                            dep_task.status = "pending"
                            dep_task.output_summary = None

                # Delete the original failed task (replaced by new ones)
                res = await db.execute(select(Task).where(Task.id == failed_task.id))
                old_task = res.scalar_one()
                await db.delete(old_task)

            await db.commit()

        recovered_any = True
        await event_bus.publish(action_id, "task.recovered", {
            "action_id": action_id,
            "original_task_id": failed_task.id,
            "original_agent_type": failed_task.agent_type,
            "replacement_agent_types": [s.agent_type for s in replacement_specs],
        })
        logger.info(
            f"[Recovery] {failed_task.agent_type} → "
            f"{[s.agent_type for s in replacement_specs]} "
            f"(task {failed_task.id[:8]})"
        )

    # Final pass: reset any remaining "Dependency failed" tasks whose root
    # cause has now been fixed (in case they weren't caught above)
    async with async_session() as db:
        res = await db.execute(select(Task).where(Task.action_id == action_id))
        stale = [
            t for t in res.scalars().all()
            if t.status == "failed" and t.output_summary == "Dependency failed"
        ]
        if stale:
            for t in stale:
                t.status = "pending"
                t.output_summary = None
            await db.commit()

    return recovered_any


async def full_replan(action_id: str, failed_info: list[str]) -> bool:
    """Delete all tasks and regenerate the plan from scratch with failure context."""
    from app.services.planner import plan_tasks

    async with async_session() as db:
        result = await db.execute(select(Action).where(Action.id == action_id))
        action = result.scalar_one()
        root_prompt = action.root_prompt

        # Delete all existing tasks for this action
        res = await db.execute(select(Task).where(Task.action_id == action_id))
        for t in res.scalars().all():
            await db.delete(t)
        await db.flush()

        # Enhance the prompt with context about what failed so the planner can avoid it
        enhanced_prompt = root_prompt
        if failed_info:
            context = "; ".join(failed_info[:3])
            enhanced_prompt += (
                f"\n\nNote: A previous attempt at this workflow failed at these steps: {context}. "
                f"Please use different agent types or strategies to avoid the same failures."
            )

        new_tasks = await plan_tasks(enhanced_prompt, action_id, db)
        if not new_tasks:
            return False
        for t in new_tasks:
            db.add(t)
        action.retry_count = 0
        await db.commit()

    return True


async def transform_to_acquisition(
    action_id: str,
    task_id: str,
    original_prompt: str,
    original_agent_type: str,
    error_message: str,
) -> bool:
    """Transform a failing task in-place into a sub_action that acquires data.

    The task keeps its ID and dependencies but becomes a sub_action whose
    child workflow will research and download the missing data.  Downstream
    tasks see the acquisition output as this task's output — no DAG rewiring
    needed.

    Returns True if the task was transformed, False if it's already a
    sub_action (prevents infinite loops).
    """
    async with async_session() as db:
        res = await db.execute(select(Task).where(Task.id == task_id))
        task = res.scalar_one()

        # Guard: if already a sub_action we already tried acquisition — bail
        if task.agent_type == "sub_action":
            return False

        acquisition_prompt = (
            f"[INPUT ACQUISITION]\n\n"
            f"A task needs specific data that could not be retrieved through "
            f"standard web search and data retrieval:\n\n"
            f"  Original task: {original_prompt}\n"
            f"  Agent type that failed: {original_agent_type}\n"
            f"  Error: {error_message[:500]}\n\n"
            f"Your goal: Figure out how to obtain this data and actually "
            f"acquire it.\n\n"
            f"Steps:\n"
            f"1. Research what Python packages, APIs, data archives, or "
            f"download methods can provide this specific data.  Think about "
            f"domain-specific tools (e.g. healpy for CMB data, astropy for "
            f"astronomical data, biopython for genomic data, netCDF4 / "
            f"xarray for climate data, etc.)\n"
            f"2. Write and execute code to download/prepare the data, saving "
            f"all output files.  Install any necessary packages.\n"
            f"3. Verify the downloaded data is valid and summarize what was "
            f"acquired, including file formats, sizes, and how to use the "
            f"data.\n\n"
            f"Save all downloaded data as files (artifacts) so downstream "
            f"tasks can access them."
        )

        task.agent_type = "sub_action"
        task.prompt = acquisition_prompt
        task.status = "pending"
        task.output_summary = None
        task.model = None
        await db.commit()

    logger.info(
        f"[Acquisition] Transformed task {task_id[:8]} from "
        f"{original_agent_type} → sub_action for data acquisition"
    )
    await event_bus.publish(action_id, "task.acquisition", {
        "task_id": task_id,
        "original_agent_type": original_agent_type,
        "reason": error_message[:300],
    })
    return True
