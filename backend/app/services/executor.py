import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Action, Artifact, Log, Task, TaskOutput
from app.services.agents.registry import get_agent_async
from app.services.event_bus import event_bus
from app.services.recovery_planner import MAX_RECOVERY_ATTEMPTS, plan_recovery

logger = logging.getLogger(__name__)

# Track running executors per action for cancellation
_running_executors: dict[str, asyncio.Task] = {}


async def invalidate_downstream(
    task_id: str, action_id: str, db: AsyncSession
):
    """BFS from edited task to invalidate all downstream tasks."""
    result = await db.execute(
        select(Task).where(Task.action_id == action_id)
    )
    all_tasks = {t.id: t for t in result.scalars().all()}

    # Build reverse dependency map: for each task, who depends on it
    dependents: dict[str, list[str]] = {}
    for t in all_tasks.values():
        for dep_id in t.dependencies:
            dependents.setdefault(dep_id, []).append(t.id)

    # BFS from task_id
    queue = list(dependents.get(task_id, []))
    visited = set()
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        task = all_tasks.get(current)
        if task:
            task.status = "pending"
            task.output_summary = None
            queue.extend(dependents.get(current, []))

    # Delete old outputs for invalidated tasks
    for tid in visited:
        result = await db.execute(
            select(TaskOutput).where(TaskOutput.task_id == tid)
        )
        for output in result.scalars().all():
            await db.delete(output)


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

    try:
        while True:  # recovery loop
            # ── inner DAG pass ──────────────────────────────────────────────
            await _run_dag_pass(action_id)

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
                    action.status = "failed"
                    await db.commit()
                    await event_bus.publish(action_id, "action.failed", {
                        "action_id": action_id,
                        "reason": "One or more tasks failed after all recovery attempts",
                    })
                    return

                current_retry = action.retry_count
                # Keep snapshot of task objects for the recovery call
                failed_snapshot = list(failed_tasks)
                all_snapshot = list(all_tasks)

            # ── attempt recovery (outside the session) ──────────────────────
            logger.info(
                f"[Executor] Recovery attempt {current_retry + 1}/{MAX_RECOVERY_ATTEMPTS} "
                f"for action {action_id} — {len(failed_snapshot)} failed task(s)"
            )
            recovered = await _attempt_recovery(action_id, failed_snapshot, all_snapshot)

            if not recovered:
                async with async_session() as db:
                    result = await db.execute(
                        select(Action).where(Action.id == action_id)
                    )
                    action = result.scalar_one()
                    action.status = "failed"
                    await db.commit()
                await event_bus.publish(action_id, "action.failed", {
                    "action_id": action_id,
                    "reason": "Recovery planning produced no replacement tasks",
                })
                return

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


async def _run_dag_pass(action_id: str):
    """Run the DAG until no tasks are ready and none are running."""
    while True:
        async with async_session() as db:
            result = await db.execute(
                select(Task).where(Task.action_id == action_id)
            )
            all_tasks = list(result.scalars().all())

            completed_ids = {t.id for t in all_tasks if t.status == "completed"}
            failed_ids = {t.id for t in all_tasks if t.status == "failed"}
            running_ids = {t.id for t in all_tasks if t.status == "running"}

            ready = []
            for t in all_tasks:
                if t.status == "pending":
                    deps_met = all(d in completed_ids for d in t.dependencies)
                    deps_failed = any(d in failed_ids for d in t.dependencies)
                    if deps_failed:
                        t.status = "failed"
                        t.output_summary = "Dependency failed"
                        await db.commit()
                        await event_bus.publish(action_id, "task.failed", {
                            "task_id": t.id,
                            "error": "Dependency failed",
                        })
                    elif deps_met:
                        ready.append(t)

            if not ready and not running_ids:
                break

            for t in ready:
                t.status = "running"
            await db.commit()

        if not ready:
            await asyncio.sleep(0.5)
            continue

        coros = [
            _run_task(action_id, t.id, t.prompt, t.agent_type, t.dependencies, t.model)
            for t in ready
        ]
        await asyncio.gather(*coros, return_exceptions=True)


async def _attempt_recovery(
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

        downstream_ids = _collect_downstream(failed_task.id, dependents)

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


def _collect_downstream(task_id: str, dependents: dict[str, list[str]]) -> set[str]:
    """BFS to collect all transitively downstream task IDs."""
    visited: set[str] = set()
    queue = list(dependents.get(task_id, []))
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        queue.extend(dependents.get(current, []))
    return visited


async def _run_task(
    action_id: str,
    task_id: str,
    prompt: str,
    agent_type: str,
    dependency_ids: list[str],
    model: str | None = None,
):
    """Run a single task with the appropriate agent."""
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

    try:
        # Gather dependency outputs (text + artifact URLs)
        dep_outputs = {}
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
                    dep_outputs[dep_id] = text

        async with async_session() as db:
            agent = await get_agent_async(agent_type, db)
        result = await agent.execute(task_id, prompt, dep_outputs, log_callback, model=model)

        # Save output
        async with async_session() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one()
            task.status = "completed"
            task.output_summary = result.get("summary", "Completed")
            if result.get("sub_action_id"):
                task.sub_action_id = result["sub_action_id"]

            task_output = TaskOutput(
                task_id=task_id,
                text=result.get("summary", "Completed"),
            )
            db.add(task_output)
            await db.commit()

        await event_bus.publish(action_id, "task.completed", {
            "task_id": task_id,
            "output_summary": result.get("summary", "Completed"),
        })

    except Exception as e:
        logger.exception(f"Task {task_id} failed")
        async with async_session() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one()
            task.status = "failed"
            task.output_summary = str(e)
            await db.commit()

        await event_bus.publish(action_id, "task.failed", {
            "task_id": task_id,
            "error": str(e),
        })
