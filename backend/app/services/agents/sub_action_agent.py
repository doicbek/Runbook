import logging
from typing import Any

from app.services.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class SubActionAgent(BaseAgent):
    """Spawns a child action with its own planner-generated DAG and runs it inline."""

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
        from app.models.task import Task
        from app.services.executor import run_action
        from app.services.planner import plan_tasks

        async with async_session() as db:
            # Determine the depth of the parent action
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

            # Build sub-prompt combining dependency context + task prompt
            context_parts = []
            for dep_id, dep_text in dependency_outputs.items():
                if dep_text:
                    context_parts.append(f"[Context from upstream task {dep_id}]\n{dep_text}")
            combined_prompt = prompt
            if context_parts:
                combined_prompt = "\n\n".join(context_parts) + "\n\n" + prompt

            # Create child action
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
            await db.flush()  # get child_action.id

            child_id = child_action.id

            # Plan child action tasks
            child_tasks = await plan_tasks(combined_prompt, child_id, db)
            for t in child_tasks:
                db.add(t)

            # Link parent task to child action
            parent_task.sub_action_id = child_id

            await db.commit()

        if log_callback:
            await log_callback(
                "info",
                f"Spawned sub-action {child_id}: {prompt[:60]}",
            )

        # Run child action (awaits completion of entire DAG)
        await run_action(child_id)

        if log_callback:
            await log_callback("info", f"Sub-action {child_id} finished")

        # Collect outputs from completed child tasks
        async with async_session() as db:
            result = await db.execute(
                select(Task)
                .where(Task.action_id == child_id, Task.status == "completed")
                .order_by(Task.created_at.desc())
            )
            completed_tasks = result.scalars().all()

        summary_parts = [t.output_summary for t in completed_tasks if t.output_summary]
        summary = summary_parts[0] if summary_parts else "Sub-action completed (no output)"

        return {"summary": summary, "sub_action_id": child_id}
