import asyncio
import json
import os
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.models import Action, Task, AgentIteration, TaskOutput, Log, Artifact
from app.schemas.action import ActionCreate, ActionListResponse, ActionResponse, ActionUpdate, PaginatedActionsResponse
from app.schemas.task import TaskResponse
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/actions", tags=["actions"])


async def _generate_title(prompt: str) -> str:
    """Generate a short title for an action using an LLM."""
    try:
        from app.services.llm_client import utility_completion

        title = await utility_completion(
            [
                {
                    "role": "system",
                    "content": "Generate a short, descriptive title (3-8 words) for the following task prompt. Return ONLY the title, no quotes, no punctuation at the end.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=30,
            temperature=0.3,
        )
        title = title.strip().strip('"\'.')
        return title or prompt[:80]
    except Exception:
        return prompt[:80]


@router.post("", response_model=ActionResponse, status_code=201)
async def create_action(body: ActionCreate, db: AsyncSession = Depends(get_db)):
    from app.services.executor import run_action as execute_action
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

    # Auto-run immediately after planning
    asyncio.create_task(execute_action(action.id))

    result = await db.execute(
        select(Action).options(selectinload(Action.tasks)).where(Action.id == action.id)
    )
    return result.scalar_one()


@router.get("", response_model=PaginatedActionsResponse)
async def list_actions(
    status: str | None = None,
    search: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    task_count_col = func.count(Task.id).label("task_count")
    query = (
        select(Action, task_count_col)
        .outerjoin(Task, Task.action_id == Action.id)
        .group_by(Action.id)
        .order_by(Action.updated_at.desc())
    )

    if status:
        query = query.where(Action.status == status)

    if search:
        pattern = f"%{search}%"
        query = query.where(
            (Action.title.ilike(pattern)) | (Action.root_prompt.ilike(pattern))
        )

    if cursor:
        from datetime import datetime, timezone
        try:
            cursor_dt = datetime.fromisoformat(cursor)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cursor format")
        query = query.where(Action.updated_at < cursor_dt)

    # Fetch one extra to determine if there are more results
    query = query.limit(limit + 1)

    result = await db.execute(query)
    rows = result.all()

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last_action = rows[-1][0]
        next_cursor = last_action.updated_at.isoformat()

    actions = []
    for action, task_count in rows:
        actions.append(
            ActionListResponse(
                id=action.id,
                title=action.title,
                root_prompt=action.root_prompt,
                status=action.status,
                created_at=action.created_at,
                updated_at=action.updated_at,
                task_count=task_count,
                parent_action_id=action.parent_action_id,
                depth=action.depth or 0,
            )
        )

    return PaginatedActionsResponse(actions=actions, next_cursor=next_cursor)


@router.get("/{action_id}/breadcrumbs")
async def get_breadcrumbs(action_id: str, db: AsyncSession = Depends(get_db)):
    """Return the parent chain for a sub-action (root first, current last)."""
    crumbs = []
    current_id = action_id
    seen = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        result = await db.execute(select(Action).where(Action.id == current_id))
        action = result.scalar_one_or_none()
        if not action:
            break
        crumbs.append({"id": action.id, "title": action.title, "depth": action.depth or 0})
        current_id = action.parent_action_id
    crumbs.reverse()  # root first
    return crumbs


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


@router.delete("/{action_id}", status_code=204)
async def delete_action(action_id: str, db: AsyncSession = Depends(get_db)):
    """Delete an action and all related data (tasks, outputs, artifacts, logs, iterations)."""
    from app.services.executor import _running_executors

    result = await db.execute(select(Action).where(Action.id == action_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    # Recursively collect all action IDs to delete (this action + sub-actions)
    action_ids_to_delete: list[str] = []
    queue = [action_id]
    while queue:
        current = queue.pop()
        action_ids_to_delete.append(current)
        child_result = await db.execute(
            select(Action.id).where(Action.parent_action_id == current)
        )
        queue.extend(child_result.scalars().all())

    # Cancel running executors and clear event history for all actions being deleted
    for aid in action_ids_to_delete:
        existing = _running_executors.get(aid)
        if existing and not existing.done():
            existing.cancel()
            try:
                await existing
            except (asyncio.CancelledError, Exception):
                pass
        event_bus.clear_history(aid)

    # Collect artifact storage paths for file cleanup
    artifact_result = await db.execute(
        select(Artifact.storage_path).where(Artifact.action_id.in_(action_ids_to_delete))
    )
    artifact_paths = [p for p in artifact_result.scalars().all() if p]

    # Delete in dependency order (children before parents)
    for aid in reversed(action_ids_to_delete):
        task_ids_result = await db.execute(
            select(Task.id).where(Task.action_id == aid)
        )
        task_ids = task_ids_result.scalars().all()

        if task_ids:
            # AgentIteration not in cascade — delete explicitly
            await db.execute(
                delete(AgentIteration).where(AgentIteration.action_id == aid)
            )

        # Delete the action — cascades handle Task, TaskOutput, Artifact (DB), Log
        action_result = await db.execute(select(Action).where(Action.id == aid))
        action_to_delete = action_result.scalar_one_or_none()
        if action_to_delete:
            await db.delete(action_to_delete)

    await db.commit()

    # Clean up artifact files on disk (after DB commit, swallow errors)
    for path in artifact_paths:
        try:
            os.unlink(path)
        except OSError:
            pass

    return Response(status_code=204)


@router.get("/{action_id}/events")
async def action_events(action_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Action).where(Action.id == action_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    # Read Last-Event-ID for reconnect replay
    last_event_id_header = request.headers.get("Last-Event-ID")
    last_event_id: int | None = None
    if last_event_id_header:
        try:
            last_event_id = int(last_event_id_header)
        except (ValueError, TypeError):
            pass

    async def event_generator():
        from app.database import async_session as get_session

        queue = event_bus.subscribe(action_id)
        try:
            if last_event_id is not None:
                # Reconnect: replay missed events from ring buffer
                missed = event_bus.replay_from(action_id, last_event_id)
                for msg in missed:
                    yield {
                        "id": str(msg["id"]),
                        "event": msg["event"],
                        "data": json.dumps(msg["data"]),
                    }
            else:
                # Fresh connection: send initial snapshot
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
                        "id": str(msg["id"]),
                        "event": msg["event"],
                        "data": json.dumps(msg["data"]),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            event_bus.unsubscribe(action_id, queue)

    return EventSourceResponse(event_generator())


@router.post("/{action_id}/save-as-template", status_code=201)
async def save_action_as_template(action_id: str, db: AsyncSession = Depends(get_db)):
    """Convenience endpoint: save a completed action as a template."""
    from app.routers.templates import save_action_as_template as _save
    return await _save(action_id, db)
