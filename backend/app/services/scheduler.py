"""Background scheduler that polls for due ActionSchedules and creates actions."""

import asyncio
import logging
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select, update

from app.database import async_session
from app.models.action import Action
from app.models.action_schedule import ActionSchedule

logger = logging.getLogger(__name__)

SCHEDULER_POLL_INTERVAL = 30  # seconds


async def _create_action_from_schedule(schedule: ActionSchedule) -> str:
    """Create and run a new action from a schedule. Returns the action ID."""
    from app.services.executor import run_action as execute_action
    from app.services.planner import plan_tasks

    async with async_session() as db:
        action = Action(
            root_prompt=schedule.root_prompt,
            title=f"{schedule.title}",
        )
        db.add(action)
        await db.flush()

        tasks = await plan_tasks(schedule.root_prompt, action.id, db)
        for t in tasks:
            db.add(t)

        await db.commit()
        action_id = action.id

    # Auto-run
    asyncio.create_task(execute_action(action_id))
    return action_id


async def _check_action_completion(action_id: str) -> str | None:
    """Check if an action has completed or failed. Returns status or None if still running."""
    async with async_session() as db:
        result = await db.execute(select(Action.status).where(Action.id == action_id))
        row = result.scalar_one_or_none()
        if row and row in ("completed", "failed"):
            return row
        return None


async def _process_due_schedules() -> None:
    """Find and execute all due schedules."""
    now = datetime.now(timezone.utc)

    async with async_session() as db:
        result = await db.execute(
            select(ActionSchedule).where(
                ActionSchedule.is_active == True,  # noqa: E712
                ActionSchedule.next_run_at <= now,
            )
        )
        due_schedules = list(result.scalars().all())

    for schedule in due_schedules:
        try:
            logger.info(
                "Scheduler: triggering schedule %s (%s)",
                schedule.id,
                schedule.title,
            )
            action_id = await _create_action_from_schedule(schedule)

            # Update schedule state
            cron = croniter(schedule.cron_expression, now)
            next_run = cron.get_next(datetime)
            # Ensure next_run is timezone-aware
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=timezone.utc)

            async with async_session() as db:
                result = await db.execute(
                    select(ActionSchedule).where(ActionSchedule.id == schedule.id)
                )
                sched = result.scalar_one()
                sched.last_run_at = now
                sched.next_run_at = next_run
                sched.run_count = sched.run_count + 1
                sched.updated_at = datetime.now(timezone.utc)
                await db.commit()

            logger.info(
                "Scheduler: created action %s for schedule %s, next run at %s",
                action_id,
                schedule.id,
                next_run.isoformat(),
            )

            # Fire-and-forget: track completion to update consecutive_failures
            asyncio.create_task(
                _track_action_completion(schedule.id, action_id)
            )

        except Exception:
            logger.exception(
                "Scheduler: failed to process schedule %s", schedule.id
            )
            # Increment consecutive_failures and still advance next_run_at
            try:
                cron = croniter(schedule.cron_expression, now)
                next_run = cron.get_next(datetime)
                if next_run.tzinfo is None:
                    next_run = next_run.replace(tzinfo=timezone.utc)

                async with async_session() as db:
                    result = await db.execute(
                        select(ActionSchedule).where(ActionSchedule.id == schedule.id)
                    )
                    sched = result.scalar_one()
                    sched.consecutive_failures = sched.consecutive_failures + 1
                    sched.last_run_at = now
                    sched.next_run_at = next_run
                    sched.updated_at = datetime.now(timezone.utc)
                    await db.commit()
            except Exception:
                logger.exception(
                    "Scheduler: failed to update schedule %s after error",
                    schedule.id,
                )


async def _track_action_completion(schedule_id: str, action_id: str) -> None:
    """Poll for action completion and update schedule consecutive_failures."""
    max_wait = 3600  # 1 hour max
    elapsed = 0
    poll_interval = 10

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        status = await _check_action_completion(action_id)
        if status is None:
            continue

        async with async_session() as db:
            result = await db.execute(
                select(ActionSchedule).where(ActionSchedule.id == schedule_id)
            )
            sched = result.scalar_one_or_none()
            if sched is None:
                return

            if status == "completed":
                sched.consecutive_failures = 0
            elif status == "failed":
                sched.consecutive_failures = sched.consecutive_failures + 1

            sched.updated_at = datetime.now(timezone.utc)
            await db.commit()

        logger.info(
            "Scheduler: action %s for schedule %s finished with status %s",
            action_id,
            schedule_id,
            status,
        )
        return

    logger.warning(
        "Scheduler: timed out waiting for action %s completion (schedule %s)",
        action_id,
        schedule_id,
    )


async def scheduler_loop() -> None:
    """Background loop that checks for due schedules every 30 seconds."""
    while True:
        try:
            await _process_due_schedules()
        except Exception:
            logger.exception("Scheduler: error in polling loop")
        await asyncio.sleep(SCHEDULER_POLL_INTERVAL)
