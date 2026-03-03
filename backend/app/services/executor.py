import asyncio
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session
from app.models import Action, Artifact, Log, Task, TaskOutput
from app.models.agent_definition import AgentDefinition
from app.models.agent_iteration import AgentIteration
from app.services.agents.exceptions import InputUnavailableError
from app.services.agents.registry import get_agent_async
from app.config import AGENT_TIMEOUTS
from app.services.dag_scheduler import run_dag_pass
from app.services.event_publisher import (
    publish_action_completed,
    publish_action_failed,
    publish_action_replanning,
    publish_action_retrying,
    publish_action_started,
    publish_llm_chunk,
    publish_log,
    publish_recovery_attempt,
    publish_recovery_exhausted,
    publish_recovery_started,
    publish_task_completed,
    publish_task_failed,
    publish_task_started,
)
from app.services.recovery_manager import (
    attempt_recovery,
    build_failure_history,
    full_replan,
    spawn_recovery_sub_action,
    triage_failure,
)
from app.services.recovery_planner import MAX_FULL_REPLANS, MAX_RECOVERY_ATTEMPTS
from app.services.skill_capture import (
    capture_correction_skill,
    capture_failure_skill,
    capture_success_skill,
)

logger = logging.getLogger(__name__)

# Track running executors per action for cancellation
_running_executors: dict[str, asyncio.Task] = {}

# Maximum number of recovery attempts per task before giving up
_MAX_RECOVERY_ATTEMPTS_PER_TASK = 3


async def run_action(action_id: str):
    """Run the DAG executor for an action. Call from a background task."""
    # Cancel any existing executor for this action
    existing = _running_executors.get(action_id)
    if existing and not existing.done():
        existing.cancel()
        try:
            await existing
        except asyncio.CancelledError:
            pass

    task = asyncio.current_task()
    if task:
        _running_executors[action_id] = task

    try:
        await _execute_dag(action_id)
    finally:
        _running_executors.pop(action_id, None)


async def _execute_dag(action_id: str):
    """DAG execution with automatic recovery on task failure."""
    async with async_session() as db:
        result = await db.execute(select(Action).where(Action.id == action_id))
        action = result.scalar_one_or_none()
        if not action:
            return
        action.status = "running"
        await db.commit()

    await publish_action_started(action_id)

    full_replan_count = 0

    try:
        while True:  # recovery loop
            await run_dag_pass(action_id, _run_task)

            async with async_session() as db:
                result = await db.execute(
                    select(Task).where(Task.action_id == action_id)
                )
                all_tasks = list(result.scalars().all())
                result = await db.execute(
                    select(Action).where(Action.id == action_id)
                )
                action = result.scalar_one()

                all_completed = all(t.status == "completed" for t in all_tasks)
                failed_tasks = [t for t in all_tasks if t.status == "failed"]

                if all_completed:
                    action.status = "completed"
                    await db.commit()
                    await publish_action_completed(action_id)
                    return

                if not failed_tasks:
                    # Tasks are still pending/paused but none running — action is stalled, not failed
                    pending_tasks = [t for t in all_tasks if t.status in ("pending", "paused")]
                    if pending_tasks:
                        # Tasks exist that could still run — don't mark as failed
                        logger.info(
                            f"[Executor] Action {action_id} has {len(pending_tasks)} pending/paused tasks "
                            f"but no failures — stopping DAG pass (may need manual resume)"
                        )
                        action.status = "draft"
                        await db.commit()
                        return
                    # Truly stuck — no failed, no pending, no running, but not all completed
                    action.status = "failed"
                    await db.commit()
                    return

                if action.retry_count >= MAX_RECOVERY_ATTEMPTS:
                    if full_replan_count >= MAX_FULL_REPLANS:
                        action.status = "failed"
                        await db.commit()
                        await publish_action_failed(
                            action_id,
                            "One or more tasks failed after all recovery attempts",
                        )
                        return
                    failed_snapshot = list(failed_tasks)
                    do_full_replan = True
                else:
                    current_retry = action.retry_count
                    failed_snapshot = list(failed_tasks)
                    all_snapshot = list(all_tasks)
                    do_full_replan = False

            if do_full_replan:
                logger.info(
                    f"[Executor] Full replan #{full_replan_count + 1} for action {action_id} "
                    f"— {len(failed_snapshot)} failed task(s)"
                )
                failed_info = [
                    f"{t.agent_type}: {(t.output_summary or t.prompt)[:120]}"
                    for t in failed_snapshot
                ]
                replanned = await full_replan(action_id, failed_info)
                if not replanned:
                    async with async_session() as db:
                        result = await db.execute(select(Action).where(Action.id == action_id))
                        action = result.scalar_one()
                        action.status = "failed"
                        await db.commit()
                    await publish_action_failed(action_id, "Full replan produced no tasks")
                    return
                full_replan_count += 1
                await publish_action_replanning(action_id, full_replan_count)
                continue

            logger.info(
                f"[Executor] Recovery attempt {current_retry + 1}/{MAX_RECOVERY_ATTEMPTS} "
                f"for action {action_id} — {len(failed_snapshot)} failed task(s)"
            )
            recovered = await attempt_recovery(action_id, failed_snapshot, all_snapshot)

            if not recovered:
                async with async_session() as db:
                    result = await db.execute(
                        select(Action).where(Action.id == action_id)
                    )
                    action = result.scalar_one()
                    action.retry_count = MAX_RECOVERY_ATTEMPTS
                    await db.commit()
                logger.info(
                    f"[Executor] Per-task recovery yielded nothing for action {action_id} "
                    f"— escalating to full replan"
                )
                continue

            async with async_session() as db:
                result = await db.execute(
                    select(Action).where(Action.id == action_id)
                )
                action = result.scalar_one()
                action.retry_count += 1
                await db.commit()

            await publish_action_retrying(action_id, current_retry + 1, MAX_RECOVERY_ATTEMPTS)

    except asyncio.CancelledError:
        async with async_session() as db:
            result = await db.execute(select(Action).where(Action.id == action_id))
            action = result.scalar_one_or_none()
            if action:
                action.status = "draft"
                await db.commit()
        raise


async def _compress_for_handoff(raw_output: str) -> str:
    """Compress verbose task output into a dense summary for downstream agents."""
    _COMPRESS_THRESHOLD = 800
    _INPUT_CAP = 4000

    if len(raw_output) <= _COMPRESS_THRESHOLD:
        return raw_output

    from app.services.llm_client import utility_completion

    system = (
        "You are a context compression assistant. Compress the following task output "
        "into a dense, information-complete summary.\n\n"
        "PRESERVE exactly:\n"
        "- All numbers, statistics, and data values\n"
        "- File paths and artifact URLs (copy verbatim)\n"
        "- Column names and tabular structure (use compact tables)\n"
        "- Key findings, conclusions, and error messages\n"
        "- Variable names, function names, and code identifiers\n\n"
        "REMOVE:\n"
        "- Verbose prose, filler phrases, and repeated information\n"
        "- Step-by-step narration of what the agent did\n"
        "- Redundant explanations\n\n"
        "Output a compact summary (300-600 tokens). Do NOT add commentary — "
        "output only the compressed content."
    )

    try:
        compressed = await utility_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": raw_output[:_INPUT_CAP]},
            ],
            max_tokens=800,
            temperature=0.0,
        )
        compressed = compressed.strip()
        if compressed:
            logger.debug(
                f"[Handoff] Compressed output from {len(raw_output)} to {len(compressed)} chars"
            )
            return compressed
    except Exception as e:
        logger.warning(f"[Handoff] Compression LLM failed ({e}), falling back to truncation")

    return raw_output[:_INPUT_CAP]


async def _gather_dep_outputs(dependency_ids: list[str]) -> dict[str, str]:
    """Collect dependency outputs (text + artifact URLs) for a task."""
    if not dependency_ids:
        return {}
    dep_outputs: dict[str, str] = {}
    from app.config import settings
    base_url = getattr(settings, "BASE_URL", "http://localhost:8001")
    async with async_session() as db:
        # Batch query: all outputs for dependencies
        result = await db.execute(
            select(TaskOutput).where(TaskOutput.task_id.in_(dependency_ids))
        )
        outputs_by_task = {o.task_id: o for o in result.scalars().all()}

        # Batch query: all artifacts for dependencies
        art_result = await db.execute(
            select(Artifact).where(Artifact.task_id.in_(dependency_ids))
        )
        artifacts_by_task: dict[str, list] = {}
        for art in art_result.scalars().all():
            artifacts_by_task.setdefault(art.task_id, []).append(art)

        for dep_id in dependency_ids:
            output = outputs_by_task.get(dep_id)
            if output:
                text = output.text or ""
                artifacts = artifacts_by_task.get(dep_id, [])
                if artifacts:
                    text += "\n\n**Artifacts from this task:**\n"
                    for art in artifacts:
                        url = f"{base_url}/artifacts/{art.id}/content"
                        if art.mime_type and art.mime_type.startswith("image/"):
                            text += f"![{art.type}]({url})\n"
                        else:
                            text += f"- [{art.type}: {art.mime_type}]({url})\n"
                text = await _compress_for_handoff(text)
                dep_outputs[dep_id] = text
    return dep_outputs


async def _run_task(
    action_id: str,
    task_id: str,
    prompt: str,
    agent_type: str,
    dependency_ids: list[str],
    model: str | None = None,
    timeout_seconds: int | None = None,
):
    """Run a single task with the appropriate agent."""
    resolved_timeout = (
        timeout_seconds
        or AGENT_TIMEOUTS.get(agent_type)
        or AGENT_TIMEOUTS.get("default", 300)
    )
    await publish_task_started(action_id, task_id)

    async def log_callback(level: str, message: str):
        for attempt in range(3):
            try:
                async with async_session() as db:
                    log = Log(
                        task_id=task_id,
                        level=level,
                        message=message,
                        timestamp=datetime.now(timezone.utc),
                    )
                    db.add(log)
                    await db.commit()
                break
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(0.2 * (attempt + 1))
                else:
                    logger.warning(f"Failed to persist log for task {task_id}: {message[:80]}")
        await publish_log(action_id, task_id, level, message)

    # Inject past lessons into the prompt
    from app.services.agents.agent_memory import load_memory
    async with async_session() as mem_db:
        memory = await load_memory(agent_type, mem_db)
    effective_prompt = prompt
    if memory:
        effective_prompt = (
            f"[Lessons from past failures — apply these to avoid repeating mistakes]\n"
            f"{memory}\n\n"
            f"[Current task]\n{prompt}"
        )
        logger.info(f"[AgentMemory] Injecting memory for {agent_type} ({len(memory)} chars)")

    # Inject proven skills for this agent type
    from app.services.agents.agent_skills import load_skills_for_agent, format_skills_for_prompt
    try:
        async with async_session() as db:
            skills = await load_skills_for_agent(agent_type, db)
        if skills:
            skills_block = format_skills_for_prompt(skills)
            effective_prompt = f"{skills_block}\n\n{effective_prompt}"
            logger.info(f"[AgentSkills] Injecting {len(skills)} skills for {agent_type}")
    except Exception:
        logger.exception(f"[AgentSkills] Failed to load skills for {agent_type}")

    dep_outputs = await _gather_dep_outputs(dependency_ids)

    # ── Primary execution attempt ─────────────────────────────────────
    start_ms = time.monotonic()
    try:
        agent = await _create_agent(action_id, task_id, agent_type, model)
        result = await asyncio.wait_for(
            agent.execute(task_id, effective_prompt, dep_outputs, log_callback, model=model),
            timeout=resolved_timeout,
        )
        await _save_task_success(action_id, task_id, result)
        return

    except asyncio.TimeoutError:
        timeout_msg = f"Task timed out after {resolved_timeout} seconds"
        logger.error(f"Task {task_id}: {timeout_msg}")
        await log_callback("error", timeout_msg)

        async with async_session() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one()
            task.status = "failed"
            task.output_summary = timeout_msg
            await db.commit()

        await publish_task_failed(action_id, task_id, timeout_msg, timeout_msg, timeout=True)
        return

    except InputUnavailableError as e:
        logger.info(f"Task {task_id} input unavailable: {e} — resetting to pending")
        async with async_session() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one()
            task.status = "pending"
            task.output_summary = None
            await db.commit()
        return

    except Exception as e:
        logger.exception(f"Task {task_id} failed")
        first_error = str(e)

        try:
            from app.services.agents.agent_memory import generate_and_save_lesson
            async with async_session() as mem_db:
                await generate_and_save_lesson(agent_type, prompt, first_error, mem_db)
        except Exception:
            pass

        capture_failure_skill(
            agent_type=agent_type,
            task_prompt=prompt,
            error=first_error,
            task_id=task_id,
            action_id=action_id,
        )

    primary_duration = int((time.monotonic() - start_ms) * 1000)

    async with async_session() as db:
        iteration = AgentIteration(
            task_id=task_id,
            action_id=action_id,
            iteration_number=1,
            loop_type="primary",
            attempt_number=0,
            reasoning=f"Primary execution of {agent_type} agent",
            tool_calls=[],
            outcome="failed",
            error=first_error[:2000],
            duration_ms=primary_duration,
        )
        db.add(iteration)
        await db.commit()

    # ── LLM-triaged recovery loop ───────────────────────────────────────
    await log_callback("warn", f"Primary agent failed: {first_error[:200]}")
    await log_callback("info", f"Starting recovery (up to {_MAX_RECOVERY_ATTEMPTS_PER_TASK} attempts, LLM-triaged)...")

    await publish_recovery_started(
        action_id, task_id, _MAX_RECOVERY_ATTEMPTS_PER_TASK, first_error[:300]
    )

    prior_attempts: list[dict] = []
    last_error = first_error

    for attempt_num in range(1, _MAX_RECOVERY_ATTEMPTS_PER_TASK + 1):
        strategy = await triage_failure(
            prompt, agent_type, last_error, attempt_num, prior_attempts
        )
        await log_callback(
            "info",
            f"Attempt {attempt_num}/{_MAX_RECOVERY_ATTEMPTS_PER_TASK}: "
            f"LLM triage chose '{strategy}'",
        )

        await publish_recovery_attempt(
            action_id, task_id, attempt_num, _MAX_RECOVERY_ATTEMPTS_PER_TASK, strategy
        )

        attempt_start = time.monotonic()
        attempt_error: str | None = None
        result = None

        if strategy == "retry":
            failure_history = [
                {"attempt": 0, "loop_type": "primary", "error": first_error, "summary": None},
                *[
                    {"attempt": p["attempt"], "loop_type": p["strategy"], "error": p["error"], "summary": None}
                    for p in prior_attempts
                ],
            ]
            history_block = build_failure_history(failure_history)
            retry_prompt = f"{history_block}\n{effective_prompt}"

            try:
                agent = await _create_agent(action_id, task_id, agent_type, model)
                result = await asyncio.wait_for(
                    agent.execute(
                        task_id, retry_prompt, dep_outputs, log_callback, model=model
                    ),
                    timeout=resolved_timeout,
                )
            except asyncio.TimeoutError:
                attempt_error = f"Task timed out after {resolved_timeout} seconds"
            except Exception as e:
                attempt_error = str(e)

        else:
            recovery_result = await spawn_recovery_sub_action(
                action_id=action_id,
                task_id=task_id,
                original_prompt=prompt,
                original_agent_type=agent_type,
                error_message=last_error,
                attempt=attempt_num,
                max_attempts=_MAX_RECOVERY_ATTEMPTS_PER_TASK,
                prior_attempts=prior_attempts,
                dep_outputs=dep_outputs,
                log_callback=log_callback,
            )
            if recovery_result is not None:
                result = recovery_result
            else:
                attempt_error = f"Recovery sub-action attempt {attempt_num} returned no result"

        attempt_duration = int((time.monotonic() - attempt_start) * 1000)

        outcome = "completed" if result is not None else "failed"
        async with async_session() as db:
            iteration = AgentIteration(
                task_id=task_id,
                action_id=action_id,
                iteration_number=attempt_num + 1,
                loop_type=strategy,
                attempt_number=attempt_num,
                reasoning=f"Attempt {attempt_num} ({strategy}): "
                          f"{'succeeded' if result else attempt_error or 'unknown error'}",
                tool_calls=[],
                outcome=outcome,
                error=(attempt_error or "")[:2000] if attempt_error else None,
                duration_ms=attempt_duration,
            )
            db.add(iteration)
            await db.commit()

        if result is not None:
            await log_callback("info", f"Attempt {attempt_num} ({strategy}) succeeded!")
            await _save_task_success(action_id, task_id, result)

            capture_correction_skill(
                agent_type=agent_type,
                task_prompt=prompt,
                error=first_error,
                successful_output=result.get("output_summary") or result.get("summary", ""),
                task_id=task_id,
                action_id=action_id,
            )
            return

        last_error = attempt_error or "Unknown error"
        prior_attempts.append({
            "attempt": attempt_num,
            "strategy": strategy,
            "error": last_error,
        })

        if attempt_num < _MAX_RECOVERY_ATTEMPTS_PER_TASK:
            await log_callback(
                "warn",
                f"Attempt {attempt_num} ({strategy}) failed: {last_error[:150]}",
            )

    # ── All attempts exhausted ─────────────────────────────────────────
    await log_callback(
        "error",
        f"All {_MAX_RECOVERY_ATTEMPTS_PER_TASK} recovery attempts failed. Task is failed.",
    )

    await publish_recovery_exhausted(
        action_id, task_id, _MAX_RECOVERY_ATTEMPTS_PER_TASK, first_error[:300]
    )

    structured_summary = (
        f"**Error:** {first_error[:500]}\n\n"
        f"**Recovery attempts:** {_MAX_RECOVERY_ATTEMPTS_PER_TASK}\n"
        + "\n".join(
            f"- Attempt {p['attempt']} ({p['strategy']}): {p['error'][:200]}"
            for p in prior_attempts
        )
    )

    async with async_session() as db:
        task_result = await db.execute(select(Task).where(Task.id == task_id))
        task = task_result.scalar_one()
        task.status = "failed"
        task.output_summary = structured_summary
        await db.commit()

    await publish_task_failed(
        action_id, task_id,
        error=first_error[:500],
        output_summary=structured_summary,
        recovery_attempts=_MAX_RECOVERY_ATTEMPTS_PER_TASK,
        recovery_history=prior_attempts,
    )


async def _create_agent(action_id: str, task_id: str, agent_type: str, model: str | None):
    """Create and configure an agent instance for execution."""
    async with async_session() as db:
        agent = await get_agent_async(agent_type, db)
        result = await db.execute(
            select(AgentDefinition).where(
                AgentDefinition.agent_type == agent_type,
                AgentDefinition.status == "active",
            )
        )
        defn = result.scalar_one_or_none()
        if defn and defn.mcp_config:
            agent.mcp_config = defn.mcp_config
        if agent.supports_streaming:
            async def _stream_cb(chunk: str) -> None:
                await publish_llm_chunk(action_id, task_id, chunk, model or agent_type)
            agent.stream_callback = _stream_cb
    return agent


async def _save_task_success(action_id: str, task_id: str, result: dict):
    """Persist a successful task result and publish the completion event."""
    output_summary = result.get("output_summary") or result.get("summary", "Completed")

    async with async_session() as db:
        task_result = await db.execute(select(Task).where(Task.id == task_id))
        task = task_result.scalar_one()
        task.status = "completed"
        task.output_summary = output_summary
        if result.get("sub_action_id"):
            task.sub_action_id = result["sub_action_id"]

        task_output = TaskOutput(
            task_id=task_id,
            text=result.get("summary", "Completed"),
            artifact_ids=result.get("artifact_ids", []),
        )
        db.add(task_output)
        await db.commit()

    await publish_task_completed(
        action_id, task_id, output_summary, result.get("artifact_ids", [])
    )

    # Fire-and-forget: auto-generate a skill from this success
    async with async_session() as db:
        task_result2 = await db.execute(select(Task).where(Task.id == task_id))
        task_obj = task_result2.scalar_one()
        capture_success_skill(
            agent_type=task_obj.agent_type,
            task_prompt=task_obj.prompt,
            output_summary=output_summary,
            task_id=task_id,
            action_id=action_id,
        )
