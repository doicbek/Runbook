import asyncio
import logging
from typing import Any

from app.services.agents.base import BaseAgent

logger = logging.getLogger(__name__)

# Maximum time (seconds) a child action is allowed to run before we give up.
_CHILD_TIMEOUT = 600  # 10 minutes


class SubActionAgent(BaseAgent):
    """Spawns a child action with its own planner-generated DAG and runs it inline.

    The child action receives the parent task's prompt (augmented with upstream
    context) and produces its own multi-step plan.  All child outputs and
    artifacts are collected and surfaced to the parent task.
    """

    async def execute(
        self,
        task_id: str,
        prompt: str,
        dependency_outputs: dict[str, Any],
        log_callback: Any = None,
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        from sqlalchemy import select

        from app.database import async_session
        from app.models.action import Action
        from app.models.artifact import Artifact
        from app.models.task import Task
        from app.models.task_output import TaskOutput
        from app.services.executor import run_action
        from app.services.planner import plan_tasks

        # ── 1. Depth check ──────────────────────────────────────────────
        async with async_session() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            parent_task = result.scalar_one()

            result = await db.execute(
                select(Action).where(Action.id == parent_task.action_id)
            )
            parent_action = result.scalar_one()

            if parent_action.depth >= 3:
                raise ValueError(
                    f"Sub-action depth limit (3) reached; parent action depth={parent_action.depth}"
                )

        # ── 2. Build combined prompt with upstream context ───────────────
        context_parts = []
        for dep_id, dep_text in dependency_outputs.items():
            if dep_text:
                context_parts.append(
                    f"[Context from upstream task {dep_id}]\n{dep_text}"
                )
        combined_prompt = prompt
        if context_parts:
            combined_prompt = "\n\n".join(context_parts) + "\n\n" + prompt

        # ── 3. Create child action ───────────────────────────────────────
        if log_callback:
            await log_callback("info", f"Creating sub-action for: {prompt[:100]}")

        async with async_session() as db:
            child_action = Action(
                title=f"Sub: {prompt[:80]}",
                root_prompt=combined_prompt,
                status="draft",
                parent_action_id=parent_action.id,
                parent_task_id=task_id,
                output_contract=prompt,
                depth=parent_action.depth + 1,
            )
            db.add(child_action)
            await db.flush()
            child_id = child_action.id

            # Plan child action tasks
            child_tasks = await plan_tasks(combined_prompt, child_id, db)
            if not child_tasks:
                raise RuntimeError("Sub-action planner returned no tasks")

            for t in child_tasks:
                db.add(t)

            # Link parent task → child action
            parent_task_ref = await db.execute(
                select(Task).where(Task.id == task_id)
            )
            pt = parent_task_ref.scalar_one()
            pt.sub_action_id = child_id

            await db.commit()

        if log_callback:
            await log_callback(
                "info",
                f"Sub-action {child_id} created with {len(child_tasks)} tasks "
                f"(depth {parent_action.depth + 1})",
            )

        # ── 4. Execute child DAG (with timeout + progress forwarding) ────
        # Forward child events to parent action's event bus so the UI
        # can show progress without a dedicated SSE connection.
        async def _forward_child_events():
            from app.services.event_bus import event_bus
            queue = event_bus.subscribe(child_id)
            try:
                while True:
                    msg = await asyncio.wait_for(queue.get(), timeout=_CHILD_TIMEOUT)
                    # Forward select events to parent action stream
                    if msg["event"] in (
                        "task.started", "task.completed", "task.failed",
                        "action.completed", "action.failed",
                    ):
                        await event_bus.publish(parent_action.id, "sub_action.progress", {
                            "parent_task_id": task_id,
                            "sub_action_id": child_id,
                            "child_event": msg["event"],
                            "child_data": msg["data"],
                        })
                    if msg["event"] in ("action.completed", "action.failed"):
                        break
            except asyncio.TimeoutError:
                pass
            finally:
                event_bus.unsubscribe(child_id, queue)

        try:
            await asyncio.wait_for(
                asyncio.gather(run_action(child_id), _forward_child_events()),
                timeout=_CHILD_TIMEOUT,
            )
        except asyncio.TimeoutError:
            if log_callback:
                await log_callback(
                    "error",
                    f"Sub-action {child_id} timed out after {_CHILD_TIMEOUT}s",
                )
            raise RuntimeError(
                f"Sub-action timed out after {_CHILD_TIMEOUT}s"
            )

        # ── 5. Collect results ───────────────────────────────────────────
        async with async_session() as db:
            # Check child action final status
            result = await db.execute(
                select(Action).where(Action.id == child_id)
            )
            child_action = result.scalar_one()

            result = await db.execute(
                select(Task).where(Task.action_id == child_id)
            )
            child_tasks_all = list(result.scalars().all())

            completed = [t for t in child_tasks_all if t.status == "completed"]
            failed = [t for t in child_tasks_all if t.status == "failed"]

            # Gather all summaries (in order, not just the first)
            summary_parts = []
            for t in child_tasks_all:
                if t.status == "completed" and t.output_summary:
                    summary_parts.append(t.output_summary)

            # Collect all child artifacts
            child_artifact_ids = []
            for t in completed:
                art_result = await db.execute(
                    select(Artifact).where(Artifact.task_id == t.id)
                )
                for art in art_result.scalars().all():
                    child_artifact_ids.append(art.id)

            # Copy child artifacts to the parent task so downstream tasks see them
            for art_id in child_artifact_ids:
                art_result = await db.execute(
                    select(Artifact).where(Artifact.id == art_id)
                )
                original = art_result.scalar_one()
                copied = Artifact(
                    task_id=task_id,
                    action_id=parent_action.id,
                    type=original.type,
                    mime_type=original.mime_type,
                    storage_path=original.storage_path,
                    size_bytes=original.size_bytes,
                )
                db.add(copied)
            await db.commit()

        # Build summary
        if child_action.status == "failed":
            fail_reasons = [
                f"- {t.prompt[:80]}: {t.output_summary or 'unknown error'}"
                for t in failed
            ]
            error_detail = "\n".join(fail_reasons[:5])
            if log_callback:
                await log_callback(
                    "error",
                    f"Sub-action {child_id} failed. {len(failed)} task(s) failed, "
                    f"{len(completed)} completed.",
                )
            # Still return partial results if any tasks completed
            if summary_parts:
                summary = (
                    f"**Sub-action partially completed** ({len(completed)}/{len(child_tasks_all)} tasks)\n\n"
                    + "\n\n---\n\n".join(summary_parts)
                    + f"\n\n**Failed tasks:**\n{error_detail}"
                )
            else:
                raise RuntimeError(
                    f"Sub-action failed entirely. {len(failed)} task(s) failed:\n{error_detail}"
                )
        else:
            if summary_parts:
                # Use the last task's summary as primary (usually the report/synthesis)
                # but include earlier summaries as context
                if len(summary_parts) == 1:
                    summary = summary_parts[0]
                else:
                    summary = summary_parts[-1]
                    # If the last summary is short, include all of them
                    if len(summary) < 500:
                        summary = "\n\n---\n\n".join(summary_parts)
            else:
                summary = "Sub-action completed (no output produced)"

        if log_callback:
            await log_callback(
                "info",
                f"Sub-action {child_id} finished: {len(completed)} completed, "
                f"{len(failed)} failed, {len(child_artifact_ids)} artifacts",
            )

        return {
            "summary": summary,
            "sub_action_id": child_id,
            "child_stats": {
                "total": len(child_tasks_all),
                "completed": len(completed),
                "failed": len(failed),
                "artifacts": len(child_artifact_ids),
            },
        }
