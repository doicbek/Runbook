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
from app.services.event_bus import event_bus
from app.services.recovery_manager import (
    attempt_recovery,
    build_failure_history,
    full_replan,
    spawn_recovery_sub_action,
    triage_failure,
)
from app.services.recovery_planner import MAX_FULL_REPLANS, MAX_RECOVERY_ATTEMPTS

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

    await event_bus.publish(action_id, "action.started", {"action_id": action_id})

    full_replan_count = 0

    try:
        while True:  # recovery loop
            # ── inner DAG pass ──────────────────────────────────────────────
            await run_dag_pass(action_id, _run_task)

            # ── evaluate outcome ────────────────────────────────────────────
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
                    await event_bus.publish(action_id, "action.completed", {
                        "action_id": action_id,
                    })
                    return

                if not failed_tasks:
                    # Shouldn't happen (no pending/running either), guard
                    action.status = "failed"
                    await db.commit()
                    return

                if action.retry_count >= MAX_RECOVERY_ATTEMPTS:
                    # Per-task recovery exhausted — try a full replan if not done yet
                    if full_replan_count >= MAX_FULL_REPLANS:
                        action.status = "failed"
                        await db.commit()
                        await event_bus.publish(action_id, "action.failed", {
                            "action_id": action_id,
                            "reason": "One or more tasks failed after all recovery attempts",
                        })
                        return
                    # Fall through to full replan below
                    failed_snapshot = list(failed_tasks)
                    do_full_replan = True
                else:
                    current_retry = action.retry_count
                    failed_snapshot = list(failed_tasks)
                    all_snapshot = list(all_tasks)
                    do_full_replan = False

            # ── full replan (replaces all tasks with a fresh plan) ───────────
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
                    await event_bus.publish(action_id, "action.failed", {
                        "action_id": action_id,
                        "reason": "Full replan produced no tasks",
                    })
                    return
                full_replan_count += 1
                await event_bus.publish(action_id, "action.replanning", {
                    "action_id": action_id,
                    "attempt": full_replan_count,
                })
                continue  # re-enter with fresh task list

            # ── per-task recovery (outside the session) ──────────────────────
            logger.info(
                f"[Executor] Recovery attempt {current_retry + 1}/{MAX_RECOVERY_ATTEMPTS} "
                f"for action {action_id} — {len(failed_snapshot)} failed task(s)"
            )
            recovered = await attempt_recovery(action_id, failed_snapshot, all_snapshot)

            if not recovered:
                # Per-task recovery found no replacements — force retry_count to
                # MAX so the next loop iteration triggers the full replan instead
                # of giving up immediately.
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
                continue  # next iteration: retry_count >= MAX → full replan path

            async with async_session() as db:
                result = await db.execute(
                    select(Action).where(Action.id == action_id)
                )
                action = result.scalar_one()
                action.retry_count += 1
                await db.commit()

            await event_bus.publish(action_id, "action.retrying", {
                "action_id": action_id,
                "attempt": current_retry + 1,
                "max_attempts": MAX_RECOVERY_ATTEMPTS,
            })
            # continue → re-enter inner DAG pass with the repaired tasks

    except asyncio.CancelledError:
        async with async_session() as db:
            result = await db.execute(select(Action).where(Action.id == action_id))
            action = result.scalar_one_or_none()
            if action:
                action.status = "draft"
                await db.commit()
        raise


async def _compress_for_handoff(raw_output: str) -> str:
    """Compress verbose task output into a dense summary for downstream agents.

    Only compresses outputs longer than 800 chars. Uses utility_completion for fast,
    cheap compression that preserves all critical data (numbers, paths, artifacts,
    column names, tabular structure). Falls back to truncation on LLM failure.
    """
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

    # Fallback: truncate raw output
    return raw_output[:_INPUT_CAP]


async def _gather_dep_outputs(dependency_ids: list[str]) -> dict[str, str]:
    """Collect dependency outputs (text + artifact URLs) for a task."""
    dep_outputs: dict[str, str] = {}
    async with async_session() as db:
        for dep_id in dependency_ids:
            result = await db.execute(
                select(TaskOutput).where(TaskOutput.task_id == dep_id)
            )
            output = result.scalar_one_or_none()
            if output:
                text = output.text or ""
                art_result = await db.execute(
                    select(Artifact).where(Artifact.task_id == dep_id)
                )
                artifacts = list(art_result.scalars().all())
                if artifacts:
                    text += "\n\n**Artifacts from this task:**\n"
                    for art in artifacts:
                        url = f"http://localhost:8001/artifacts/{art.id}/content"
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
    """Run a single task with the appropriate agent.

    On failure, enters a retry loop that re-invokes the same agent with
    augmented prompt containing structured failure history. Creates
    AgentIteration records for each retry attempt.
    """
    # Resolve timeout: task override > agent-type default > global default
    resolved_timeout = (
        timeout_seconds
        or AGENT_TIMEOUTS.get(agent_type)
        or AGENT_TIMEOUTS.get("default", 300)
    )
    await event_bus.publish(action_id, "task.started", {
        "task_id": task_id,
        "action_id": action_id,
    })

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
        await event_bus.publish(action_id, "log.append", {
            "task_id": task_id,
            "level": level,
            "message": message,
        })

    # Inject past lessons into the prompt so the agent can avoid repeating mistakes
    from app.services.agents.agent_memory import load_memory
    memory = load_memory(agent_type)
    effective_prompt = prompt
    if memory:
        effective_prompt = (
            f"[Lessons from past failures — apply these to avoid repeating mistakes]\n"
            f"{memory}\n\n"
            f"[Current task]\n{prompt}"
        )
        logger.info(f"[AgentMemory] Injecting memory for {agent_type} ({len(memory)} chars)")

    # Inject proven skills for this agent type (self-improving knowledge base)
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

    # Gather dependency outputs once (shared across retries)
    dep_outputs = await _gather_dep_outputs(dependency_ids)

    # ── Primary execution attempt (attempt_number=0) ─────────────────────
    start_ms = time.monotonic()
    try:
        async with async_session() as db:
            agent = await get_agent_async(agent_type, db)
            # Attach MCP config from agent definition if present
            result = await db.execute(
                select(AgentDefinition).where(
                    AgentDefinition.agent_type == agent_type,
                    AgentDefinition.status == "active",
                )
            )
            defn = result.scalar_one_or_none()
            if defn and defn.mcp_config:
                agent.mcp_config = defn.mcp_config
            # Attach stream callback for agents that support streaming
            if agent.supports_streaming:
                async def _stream_cb(chunk: str) -> None:
                    await event_bus.publish(action_id, "task.llm_chunk", {
                        "task_id": task_id,
                        "chunk": chunk,
                        "model": model or agent_type,
                    })
                agent.stream_callback = _stream_cb
        result = await asyncio.wait_for(
            agent.execute(task_id, effective_prompt, dep_outputs, log_callback, model=model),
            timeout=resolved_timeout,
        )

        # Success — save output and return
        await _save_task_success(action_id, task_id, result)
        return

    except asyncio.TimeoutError:
        timeout_msg = f"Task timed out after {resolved_timeout} seconds"
        logger.error(f"Task {task_id}: {timeout_msg}")
        await log_callback("error", timeout_msg)

        # Mark task as failed immediately — no retry for timeouts
        async with async_session() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one()
            task.status = "failed"
            task.output_summary = timeout_msg
            await db.commit()

        await event_bus.publish(action_id, "task.failed", {
            "task_id": task_id,
            "error": timeout_msg,
            "output_summary": timeout_msg,
            "timeout": True,
        })
        return

    except InputUnavailableError as e:
        logger.info(f"Task {task_id} input unavailable: {e}")
        first_error = str(e)

    except Exception as e:
        logger.exception(f"Task {task_id} failed")
        first_error = str(e)

        # Save lesson for future runs
        try:
            from app.services.agents.agent_memory import generate_and_save_lesson
            await generate_and_save_lesson(agent_type, prompt, first_error)
        except Exception:
            pass

        # Generate error pattern skill for self-improvement
        try:
            from app.services.agents.agent_skills import generate_skill_from_failure
            asyncio.create_task(generate_skill_from_failure(
                agent_type=agent_type,
                task_prompt=prompt,
                error=first_error,
                task_id=task_id,
                action_id=action_id,
            ))
        except Exception:
            pass

    primary_duration = int((time.monotonic() - start_ms) * 1000)

    # Record primary attempt failure as an AgentIteration
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
    # An LLM decides per-attempt whether to retry (same agent, augmented
    # prompt) or spawn a recovery sub-action (full re-plan with different
    # approach).  This avoids blindly retrying deterministic failures.
    await log_callback("warn", f"Primary agent failed: {first_error[:200]}")
    await log_callback("info", f"Starting recovery (up to {_MAX_RECOVERY_ATTEMPTS_PER_TASK} attempts, LLM-triaged)...")

    await event_bus.publish(action_id, "task.recovery.started", {
        "task_id": task_id,
        "max_attempts": _MAX_RECOVERY_ATTEMPTS_PER_TASK,
        "original_error": first_error[:300],
    })

    prior_attempts: list[dict] = []
    last_error = first_error

    for attempt_num in range(1, _MAX_RECOVERY_ATTEMPTS_PER_TASK + 1):
        # ── Triage: ask LLM which strategy to use ────────────────────
        strategy = await triage_failure(
            prompt, agent_type, last_error, attempt_num, prior_attempts
        )
        await log_callback(
            "info",
            f"Attempt {attempt_num}/{_MAX_RECOVERY_ATTEMPTS_PER_TASK}: "
            f"LLM triage chose '{strategy}'",
        )

        await event_bus.publish(action_id, "task.recovery.attempt", {
            "task_id": task_id,
            "attempt": attempt_num,
            "max_attempts": _MAX_RECOVERY_ATTEMPTS_PER_TASK,
            "strategy": strategy,
        })

        attempt_start = time.monotonic()
        attempt_error: str | None = None
        result = None

        if strategy == "retry":
            # ── Retry: same agent, augmented prompt ──────────────────
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
                async with async_session() as db:
                    agent = await get_agent_async(agent_type, db)
                    # Attach MCP config from agent definition if present
                    defn_result = await db.execute(
                        select(AgentDefinition).where(
                            AgentDefinition.agent_type == agent_type,
                            AgentDefinition.status == "active",
                        )
                    )
                    defn = defn_result.scalar_one_or_none()
                    if defn and defn.mcp_config:
                        agent.mcp_config = defn.mcp_config
                    if agent.supports_streaming:
                        async def _retry_stream_cb(chunk: str) -> None:
                            await event_bus.publish(action_id, "task.llm_chunk", {
                                "task_id": task_id,
                                "chunk": chunk,
                                "model": model or agent_type,
                            })
                        agent.stream_callback = _retry_stream_cb
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
            # ── Recovery: spawn sub-action with full re-planning ─────
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

        # ── Record iteration ─────────────────────────────────────────
        outcome = "completed" if result is not None else "failed"
        async with async_session() as db:
            iteration = AgentIteration(
                task_id=task_id,
                action_id=action_id,
                iteration_number=attempt_num + 1,  # primary was 1
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

            # Generate correction skill — captures what fixed the failure
            try:
                from app.services.agents.agent_skills import generate_correction_skill
                asyncio.create_task(generate_correction_skill(
                    agent_type=agent_type,
                    task_prompt=prompt,
                    error=first_error,
                    successful_output=result.get("output_summary") or result.get("summary", ""),
                    task_id=task_id,
                    action_id=action_id,
                ))
            except Exception:
                pass
            return

        # Failed — record and continue
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

    # ── All attempts exhausted — mark as truly failed ─────────────────
    await log_callback(
        "error",
        f"All {_MAX_RECOVERY_ATTEMPTS_PER_TASK} recovery attempts failed. Task is failed.",
    )

    await event_bus.publish(action_id, "task.recovery.exhausted", {
        "task_id": task_id,
        "attempts": _MAX_RECOVERY_ATTEMPTS_PER_TASK,
        "original_error": first_error[:300],
    })

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

    await event_bus.publish(action_id, "task.failed", {
        "task_id": task_id,
        "error": first_error[:500],
        "output_summary": structured_summary,
        "recovery_attempts": _MAX_RECOVERY_ATTEMPTS_PER_TASK,
        "recovery_history": prior_attempts,
    })


async def _save_task_success(action_id: str, task_id: str, result: dict):
    """Persist a successful task result and publish the completion event."""
    async with async_session() as db:
        task_result = await db.execute(select(Task).where(Task.id == task_id))
        task = task_result.scalar_one()
        task.status = "completed"
        # Prefer output_summary if agent provided one, else fall back to summary
        task.output_summary = result.get("output_summary") or result.get("summary", "Completed")
        if result.get("sub_action_id"):
            task.sub_action_id = result["sub_action_id"]

        task_output = TaskOutput(
            task_id=task_id,
            text=result.get("summary", "Completed"),
            artifact_ids=result.get("artifact_ids", []),
        )
        db.add(task_output)
        await db.commit()

    await event_bus.publish(action_id, "task.completed", {
        "task_id": task_id,
        "output_summary": result.get("output_summary") or result.get("summary", "Completed"),
        "artifact_ids": result.get("artifact_ids", []),
    })

    # Fire-and-forget: auto-generate a skill from this success
    try:
        from app.services.agents.agent_skills import generate_skill_from_success
        async with async_session() as db:
            task_result2 = await db.execute(select(Task).where(Task.id == task_id))
            task_obj = task_result2.scalar_one()
            asyncio.create_task(generate_skill_from_success(
                agent_type=task_obj.agent_type,
                task_prompt=task_obj.prompt,
                output_summary=result.get("output_summary") or result.get("summary", "Completed"),
                task_id=task_id,
                action_id=action_id,
            ))
    except Exception:
        logger.debug(f"[AgentSkills] Failed to schedule skill generation for task {task_id}")
