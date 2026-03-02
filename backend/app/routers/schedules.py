"""CRUD router for ActionSchedule management."""

import asyncio
import uuid
from datetime import datetime, timezone

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.action import Action
from app.models.action_schedule import ActionSchedule

router = APIRouter(prefix="/schedules", tags=["schedules"])


# --- Pydantic schemas ---

class ScheduleResponse(BaseModel):
    id: str
    title: str
    root_prompt: str
    cron_expression: str
    is_active: bool
    last_run_at: datetime | None = None
    next_run_at: datetime
    run_count: int
    consecutive_failures: int
    template_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ScheduleDetailResponse(ScheduleResponse):
    recent_actions: list[dict] = []


class ScheduleCreate(BaseModel):
    title: str
    root_prompt: str
    cron_expression: str
    is_active: bool = True
    template_id: str | None = None


class ScheduleUpdate(BaseModel):
    title: str | None = None
    root_prompt: str | None = None
    cron_expression: str | None = None
    is_active: bool | None = None


def _schedule_to_response(s: ActionSchedule) -> ScheduleResponse:
    return ScheduleResponse(
        id=s.id,
        title=s.title,
        root_prompt=s.root_prompt,
        cron_expression=s.cron_expression,
        is_active=s.is_active,
        last_run_at=s.last_run_at,
        next_run_at=s.next_run_at,
        run_count=s.run_count,
        consecutive_failures=s.consecutive_failures,
        template_id=s.template_id,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _validate_cron(expression: str) -> None:
    """Validate a cron expression, raise 400 if invalid."""
    try:
        croniter(expression)
    except (ValueError, KeyError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid cron expression: {e}",
        )


# --- Endpoints ---

@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ActionSchedule).order_by(ActionSchedule.created_at.desc())
    )
    schedules = result.scalars().all()
    return [_schedule_to_response(s) for s in schedules]


@router.get("/{schedule_id}", response_model=ScheduleDetailResponse)
async def get_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ActionSchedule).where(ActionSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Get recent actions created by this schedule (last 5 by title match)
    # Actions created by the scheduler use the schedule title
    result = await db.execute(
        select(Action)
        .where(Action.title == schedule.title)
        .order_by(Action.created_at.desc())
        .limit(5)
    )
    recent_actions = result.scalars().all()

    resp = ScheduleDetailResponse(
        id=schedule.id,
        title=schedule.title,
        root_prompt=schedule.root_prompt,
        cron_expression=schedule.cron_expression,
        is_active=schedule.is_active,
        last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at,
        run_count=schedule.run_count,
        consecutive_failures=schedule.consecutive_failures,
        template_id=schedule.template_id,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
        recent_actions=[
            {
                "id": a.id,
                "title": a.title,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in recent_actions
        ],
    )
    return resp


@router.post("", response_model=ScheduleResponse, status_code=201)
async def create_schedule(body: ScheduleCreate, db: AsyncSession = Depends(get_db)):
    _validate_cron(body.cron_expression)

    now = datetime.now(timezone.utc)
    cron = croniter(body.cron_expression, now)
    next_run = cron.get_next(datetime)
    if next_run.tzinfo is None:
        next_run = next_run.replace(tzinfo=timezone.utc)

    schedule = ActionSchedule(
        id=str(uuid.uuid4()),
        title=body.title,
        root_prompt=body.root_prompt,
        cron_expression=body.cron_expression,
        is_active=body.is_active,
        next_run_at=next_run,
        template_id=body.template_id,
        created_at=now,
        updated_at=now,
    )
    db.add(schedule)
    await db.commit()
    return _schedule_to_response(schedule)


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ActionSchedule).where(ActionSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if body.title is not None:
        schedule.title = body.title
    if body.root_prompt is not None:
        schedule.root_prompt = body.root_prompt
    if body.is_active is not None:
        schedule.is_active = body.is_active
    if body.cron_expression is not None:
        _validate_cron(body.cron_expression)
        schedule.cron_expression = body.cron_expression
        # Recompute next_run_at on cron change
        now = datetime.now(timezone.utc)
        cron = croniter(body.cron_expression, now)
        next_run = cron.get_next(datetime)
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=timezone.utc)
        schedule.next_run_at = next_run

    schedule.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _schedule_to_response(schedule)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ActionSchedule).where(ActionSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.delete(schedule)
    await db.commit()
    return Response(status_code=204)


@router.post("/{schedule_id}/run-now", response_model=ScheduleResponse)
async def run_schedule_now(schedule_id: str, db: AsyncSession = Depends(get_db)):
    """Trigger immediate run of a schedule outside of its cron timing."""
    from app.services.executor import run_action as execute_action
    from app.services.planner import plan_tasks

    result = await db.execute(
        select(ActionSchedule).where(ActionSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Create and run the action
    action = Action(
        root_prompt=schedule.root_prompt,
        title=schedule.title,
    )
    db.add(action)
    await db.flush()

    tasks = await plan_tasks(schedule.root_prompt, action.id, db)
    for t in tasks:
        db.add(t)

    # Update schedule metadata
    now = datetime.now(timezone.utc)
    schedule.last_run_at = now
    schedule.run_count = schedule.run_count + 1
    schedule.updated_at = now

    await db.commit()

    action_id = action.id
    schedule_id_for_tracking = schedule.id

    # Auto-run
    asyncio.create_task(execute_action(action_id))

    # Track completion for consecutive_failures
    asyncio.create_task(
        _track_manual_run_completion(schedule_id_for_tracking, action_id)
    )

    return _schedule_to_response(schedule)


async def _track_manual_run_completion(schedule_id: str, action_id: str) -> None:
    """Track completion of a manually triggered run to update consecutive_failures."""
    from app.database import async_session

    max_wait = 3600
    elapsed = 0
    poll_interval = 10

    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        async with async_session() as db:
            result = await db.execute(
                select(Action.status).where(Action.id == action_id)
            )
            status = result.scalar_one_or_none()
            if status not in ("completed", "failed"):
                continue

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
        return
