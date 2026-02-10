import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.models import Action, Task
from app.schemas.action import ActionCreate, ActionListResponse, ActionResponse, ActionUpdate
from app.schemas.task import TaskResponse
from app.services.event_bus import event_bus

router = APIRouter(prefix="/actions", tags=["actions"])


async def _generate_title(prompt: str) -> str:
    """Generate a short title for an action using an LLM."""
    from app.config import settings

    if not settings.OPENAI_API_KEY:
        return prompt[:80]

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Generate a short, descriptive title (3-8 words) for the following task prompt. Return ONLY the title, no quotes, no punctuation at the end.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=30,
            temperature=0.3,
        )
        title = (response.choices[0].message.content or "").strip().strip('"\'.')
        return title or prompt[:80]
    except Exception:
        return prompt[:80]


@router.post("", response_model=ActionResponse, status_code=201)
async def create_action(body: ActionCreate, db: AsyncSession = Depends(get_db)):
    from app.services.planner import plan_tasks

    title = body.title if body.title else await _generate_title(body.root_prompt)

    action = Action(
        root_prompt=body.root_prompt,
        title=title,
    )
    db.add(action)
    await db.flush()

    tasks = await plan_tasks(body.root_prompt, action.id, db)
    for t in tasks:
        db.add(t)

    await db.commit()

    result = await db.execute(
        select(Action).options(selectinload(Action.tasks)).where(Action.id == action.id)
    )
    return result.scalar_one()


@router.get("", response_model=list[ActionListResponse])
async def list_actions(
    status: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    query = select(Action).order_by(Action.updated_at.desc()).limit(limit)
    if status:
        query = query.where(Action.status == status)
    result = await db.execute(query)
    actions = result.scalars().all()

    response = []
    for action in actions:
        count_result = await db.execute(
            select(func.count()).select_from(Task).where(Task.action_id == action.id)
        )
        task_count = count_result.scalar() or 0
        response.append(
            ActionListResponse(
                id=action.id,
                title=action.title,
                root_prompt=action.root_prompt,
                status=action.status,
                created_at=action.created_at,
                updated_at=action.updated_at,
                task_count=task_count,
            )
        )
    return response


@router.get("/{action_id}", response_model=ActionResponse)
async def get_action(action_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Action).options(selectinload(Action.tasks)).where(Action.id == action_id)
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return action


@router.patch("/{action_id}", response_model=ActionResponse)
async def update_action(
    action_id: str, body: ActionUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Action).options(selectinload(Action.tasks)).where(Action.id == action_id)
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    if body.title is not None:
        action.title = body.title
    if body.root_prompt is not None:
        action.root_prompt = body.root_prompt

    await db.commit()
    await db.refresh(action)
    return action


@router.post("/{action_id}/run", response_model=ActionResponse)
async def run_action(action_id: str, db: AsyncSession = Depends(get_db)):
    from app.services.executor import run_action as execute_action

    result = await db.execute(
        select(Action).options(selectinload(Action.tasks)).where(Action.id == action_id)
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    # Check if there are any pending tasks
    has_pending = any(t.status == "pending" for t in action.tasks)
    if not has_pending:
        raise HTTPException(status_code=400, detail="No pending tasks to run")

    # Launch executor in background
    asyncio.create_task(execute_action(action_id))

    # Return current state
    await db.refresh(action)
    return action


@router.get("/{action_id}/events")
async def action_events(action_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Action).where(Action.id == action_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    async def event_generator():
        from app.database import async_session as get_session

        queue = event_bus.subscribe(action_id)
        try:
            # Send initial snapshot
            async with get_session() as snap_db:
                result = await snap_db.execute(
                    select(Action).options(selectinload(Action.tasks)).where(Action.id == action_id)
                )
                snap_action = result.scalar_one_or_none()
                if snap_action:
                    tasks_data = [TaskResponse.model_validate(t).model_dump(mode="json") for t in snap_action.tasks]
                    yield {
                        "event": "snapshot",
                        "data": json.dumps({
                            "action_id": snap_action.id,
                            "status": snap_action.status,
                            "tasks": tasks_data,
                        }),
                    }

            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": msg["event"],
                        "data": json.dumps(msg["data"]),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            event_bus.unsubscribe(action_id, queue)

    return EventSourceResponse(event_generator())
