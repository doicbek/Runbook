"""Helper functions that wrap event_bus.publish with correct payloads.

Extracted from executor.py to reduce its size and centralise event formatting.
"""

from app.services.event_bus import event_bus


async def publish_task_started(action_id: str, task_id: str) -> None:
    await event_bus.publish(action_id, "task.started", {
        "task_id": task_id,
        "action_id": action_id,
    })


async def publish_task_completed(
    action_id: str,
    task_id: str,
    output_summary: str,
    artifact_ids: list[str] | None = None,
) -> None:
    await event_bus.publish(action_id, "task.completed", {
        "task_id": task_id,
        "output_summary": output_summary,
        "artifact_ids": artifact_ids or [],
    })


async def publish_task_failed(
    action_id: str,
    task_id: str,
    error: str,
    output_summary: str | None = None,
    timeout: bool = False,
    recovery_attempts: int | None = None,
    recovery_history: list[dict] | None = None,
) -> None:
    payload: dict = {
        "task_id": task_id,
        "error": error,
    }
    if output_summary is not None:
        payload["output_summary"] = output_summary
    if timeout:
        payload["timeout"] = True
    if recovery_attempts is not None:
        payload["recovery_attempts"] = recovery_attempts
    if recovery_history is not None:
        payload["recovery_history"] = recovery_history
    await event_bus.publish(action_id, "task.failed", payload)


async def publish_log(
    action_id: str, task_id: str, level: str, message: str
) -> None:
    await event_bus.publish(action_id, "log.append", {
        "task_id": task_id,
        "level": level,
        "message": message,
    })


async def publish_action_started(action_id: str) -> None:
    await event_bus.publish(action_id, "action.started", {"action_id": action_id})


async def publish_action_completed(action_id: str) -> None:
    await event_bus.publish(action_id, "action.completed", {"action_id": action_id})


async def publish_action_failed(action_id: str, reason: str) -> None:
    await event_bus.publish(action_id, "action.failed", {
        "action_id": action_id,
        "reason": reason,
    })


async def publish_action_replanning(action_id: str, attempt: int) -> None:
    await event_bus.publish(action_id, "action.replanning", {
        "action_id": action_id,
        "attempt": attempt,
    })


async def publish_action_retrying(
    action_id: str, attempt: int, max_attempts: int
) -> None:
    await event_bus.publish(action_id, "action.retrying", {
        "action_id": action_id,
        "attempt": attempt,
        "max_attempts": max_attempts,
    })


async def publish_recovery_started(
    action_id: str, task_id: str, max_attempts: int, original_error: str
) -> None:
    await event_bus.publish(action_id, "task.recovery.started", {
        "task_id": task_id,
        "max_attempts": max_attempts,
        "original_error": original_error,
    })


async def publish_recovery_attempt(
    action_id: str, task_id: str, attempt: int, max_attempts: int, strategy: str
) -> None:
    await event_bus.publish(action_id, "task.recovery.attempt", {
        "task_id": task_id,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "strategy": strategy,
    })


async def publish_recovery_exhausted(
    action_id: str, task_id: str, attempts: int, original_error: str
) -> None:
    await event_bus.publish(action_id, "task.recovery.exhausted", {
        "task_id": task_id,
        "attempts": attempts,
        "original_error": original_error,
    })


async def publish_llm_chunk(
    action_id: str, task_id: str, chunk: str, model: str
) -> None:
    await event_bus.publish(action_id, "task.llm_chunk", {
        "task_id": task_id,
        "chunk": chunk,
        "model": model,
    })
