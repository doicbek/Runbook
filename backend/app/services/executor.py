import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Action, Artifact, Log, Task, TaskOutput
from app.services.agents.registry import get_agent_async
from app.services.event_bus import event_bus

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
    """Core DAG execution loop."""
    async with async_session() as db:
        # Set action to running
        result = await db.execute(select(Action).where(Action.id == action_id))
        action = result.scalar_one_or_none()
        if not action:
            return
        action.status = "running"
        await db.commit()

    await event_bus.publish(action_id, "action.started", {"action_id": action_id})

    try:
        while True:
            async with async_session() as db:
                result = await db.execute(
                    select(Task).where(Task.action_id == action_id)
                )
                all_tasks = list(result.scalars().all())

                completed_ids = {t.id for t in all_tasks if t.status == "completed"}
                failed_ids = {t.id for t in all_tasks if t.status == "failed"}
                running_ids = {t.id for t in all_tasks if t.status == "running"}

                # Find ready tasks: pending + all deps completed
                ready = []
                for t in all_tasks:
                    if t.status == "pending":
                        deps_met = all(d in completed_ids for d in t.dependencies)
                        # Check no deps failed
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
                    # Nothing more to do
                    break

                # Mark ready tasks as running
                for t in ready:
                    t.status = "running"
                await db.commit()

            if not ready:
                # Wait for running tasks to finish
                await asyncio.sleep(0.5)
                continue

            # Dispatch ready tasks in parallel
            coros = [_run_task(action_id, t.id, t.prompt, t.agent_type, t.dependencies, t.model) for t in ready]
            await asyncio.gather(*coros, return_exceptions=True)

        # Check final status
        async with async_session() as db:
            result = await db.execute(
                select(Task).where(Task.action_id == action_id)
            )
            all_tasks = list(result.scalars().all())
            any_failed = any(t.status == "failed" for t in all_tasks)
            all_completed = all(t.status == "completed" for t in all_tasks)

            result = await db.execute(select(Action).where(Action.id == action_id))
            action = result.scalar_one()

            if any_failed:
                action.status = "failed"
                await db.commit()
                await event_bus.publish(action_id, "action.failed", {
                    "action_id": action_id,
                    "reason": "One or more tasks failed",
                })
            elif all_completed:
                action.status = "completed"
                await db.commit()
                await event_bus.publish(action_id, "action.completed", {
                    "action_id": action_id,
                })
            else:
                action.status = "failed"
                await db.commit()

    except asyncio.CancelledError:
        async with async_session() as db:
            result = await db.execute(select(Action).where(Action.id == action_id))
            action = result.scalar_one_or_none()
            if action:
                action.status = "draft"
                await db.commit()
        raise


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
                    # Append artifact image URLs so downstream agents can reference them
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
