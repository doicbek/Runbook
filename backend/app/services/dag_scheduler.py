"""DAG scheduling logic extracted from executor.py.

Functions for running DAG passes, invalidating downstream tasks,
and collecting downstream task IDs.
"""

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Task, TaskOutput
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)


async def invalidate_downstream(
    task_id: str, action_id: str, db: AsyncSession
) -> None:
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
    queue = deque(dependents.get(task_id, []))
    visited: set[str] = set()
    while queue:
        current = queue.popleft()
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


# Type for the task runner callback passed from executor
TaskRunnerFn = Callable[
    [str, str, str, str, list[str], str | None, int | None],
    Awaitable[None],
]


async def run_dag_pass(
    action_id: str,
    task_runner: TaskRunnerFn,
) -> None:
    """Run the DAG until no tasks are ready and none are running.

    Args:
        action_id: The action whose tasks to execute.
        task_runner: Async callable with signature
            (action_id, task_id, prompt, agent_type, dependencies, model, timeout_seconds)
            that executes a single task.
    """
    _MAX_DAG_ITERATIONS = 500
    iteration_count = 0
    while True:
        iteration_count += 1
        if iteration_count > _MAX_DAG_ITERATIONS:
            logger.error(f"DAG scheduler exceeded {_MAX_DAG_ITERATIONS} iterations for action {action_id}")
            break

        async with async_session() as db:
            result = await db.execute(
                select(Task).where(Task.action_id == action_id)
            )
            all_tasks = list(result.scalars().all())

            completed_ids = {t.id for t in all_tasks if t.status == "completed"}
            failed_ids = {t.id for t in all_tasks if t.status == "failed"}
            running_ids = {t.id for t in all_tasks if t.status == "running"}

            ready = []
            dep_failed_tasks = []
            for t in all_tasks:
                if t.status == "pending":
                    deps_met = all(d in completed_ids for d in t.dependencies)
                    deps_failed = any(d in failed_ids for d in t.dependencies)
                    if deps_failed:
                        t.status = "failed"
                        t.output_summary = "Dependency failed"
                        dep_failed_tasks.append(t)
                    elif deps_met:
                        ready.append(t)

            if dep_failed_tasks:
                await db.commit()
                for t in dep_failed_tasks:
                    await event_bus.publish(action_id, "task.failed", {
                        "task_id": t.id,
                        "error": "Dependency failed",
                        "output_summary": "Dependency failed",
                    })

            if not ready and not running_ids:
                break

            for t in ready:
                t.status = "running"
            await db.commit()

        if not ready:
            await asyncio.sleep(0.5)
            continue

        coros = [
            task_runner(action_id, t.id, t.prompt, t.agent_type, t.dependencies, t.model, t.timeout_seconds)
            for t in ready
        ]
        await asyncio.gather(*coros, return_exceptions=True)


def collect_downstream(task_id: str, dependents: dict[str, list[str]]) -> set[str]:
    """BFS to collect all transitively downstream task IDs."""
    visited: set[str] = set()
    queue = deque(dependents.get(task_id, []))
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(dependents.get(current, []))
    return visited
