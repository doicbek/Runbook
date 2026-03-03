import asyncio
import json
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.action import Action
from app.models.action_template import ActionTemplate
from app.schemas.action import ActionResponse

router = APIRouter(prefix="/templates", tags=["templates"])


def _escape_like(s: str) -> str:
    return re.sub(r'([%_\\])', r'\\\1', s)


# --- Pydantic schemas ---

class TemplateListItem(BaseModel):
    id: str
    title: str
    description: str | None = None
    root_prompt: str
    tags: list[str] = []
    source_action_id: str | None = None
    usage_count: int = 0
    created_at: datetime
    updated_at: datetime


class TemplateDetail(TemplateListItem):
    pass


class TemplateCreate(BaseModel):
    title: str
    description: str | None = None
    root_prompt: str
    tags: list[str] = []


class TemplateUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None


def _template_to_response(t: ActionTemplate) -> TemplateListItem:
    tags: list[str] = []
    if t.tags:
        try:
            tags = json.loads(t.tags)
        except (json.JSONDecodeError, TypeError):
            tags = []
    return TemplateListItem(
        id=t.id,
        title=t.title,
        description=t.description,
        root_prompt=t.root_prompt,
        tags=tags,
        source_action_id=t.source_action_id,
        usage_count=t.usage_count,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


# --- Endpoints ---

@router.get("", response_model=list[TemplateListItem])
async def list_templates(
    tag: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ActionTemplate).order_by(ActionTemplate.updated_at.desc())

    if search:
        pattern = f"%{_escape_like(search)}%"
        query = query.where(
            (ActionTemplate.title.ilike(pattern)) | (ActionTemplate.description.ilike(pattern))
        )

    result = await db.execute(query)
    templates = result.scalars().all()

    items = [_template_to_response(t) for t in templates]

    # Filter by tag in Python (tags stored as JSON string)
    if tag:
        items = [item for item in items if tag in item.tags]

    return items


@router.get("/{template_id}", response_model=TemplateDetail)
async def get_template(template_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ActionTemplate).where(ActionTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_to_response(template)


@router.post("", response_model=TemplateDetail, status_code=201)
async def create_template(body: TemplateCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    template = ActionTemplate(
        id=str(uuid.uuid4()),
        title=body.title,
        description=body.description,
        root_prompt=body.root_prompt,
        tags=json.dumps(body.tags) if body.tags else "[]",
        created_at=now,
        updated_at=now,
    )
    db.add(template)
    await db.commit()
    return _template_to_response(template)


@router.patch("/{template_id}", response_model=TemplateDetail)
async def update_template(
    template_id: str,
    body: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ActionTemplate).where(ActionTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if body.title is not None:
        template.title = body.title
    if body.description is not None:
        template.description = body.description
    if body.tags is not None:
        template.tags = json.dumps(body.tags)

    template.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _template_to_response(template)


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ActionTemplate).where(ActionTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    await db.delete(template)
    await db.commit()
    return Response(status_code=204)


@router.post("/{template_id}/use", response_model=ActionResponse, status_code=201)
async def use_template(template_id: str, db: AsyncSession = Depends(get_db)):
    """Create a new action from a template and increment usage_count."""
    from app.services.executor import run_action as execute_action
    from app.services.planner import plan_tasks

    result = await db.execute(
        select(ActionTemplate).where(ActionTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Create the action
    action = Action(
        root_prompt=template.root_prompt,
        title=template.title,
    )
    db.add(action)
    await db.flush()

    tasks = await plan_tasks(template.root_prompt, action.id, db)
    for t in tasks:
        db.add(t)

    # Increment usage count
    template.usage_count = (template.usage_count or 0) + 1
    template.updated_at = datetime.now(timezone.utc)

    await db.commit()

    # Auto-run
    asyncio.create_task(execute_action(action.id))

    result = await db.execute(
        select(Action).options(selectinload(Action.tasks)).where(Action.id == action.id)
    )
    return result.scalar_one()


@router.post("/from-action/{action_id}", response_model=TemplateDetail, status_code=201)
async def save_action_as_template(action_id: str, db: AsyncSession = Depends(get_db)):
    """Save a completed action as a template with auto-generated title/description."""
    result = await db.execute(select(Action).where(Action.id == action_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    # Generate title and description via LLM
    title = action.title or action.root_prompt[:80]
    description = ""
    try:
        from app.services.llm_client import utility_completion

        resp = await utility_completion(
            [
                {
                    "role": "system",
                    "content": "Generate a JSON object with 'title' (3-8 words, template-style) and 'description' (1-2 sentences explaining what this template does). Return ONLY valid JSON.",
                },
                {"role": "user", "content": f"Action prompt: {action.root_prompt}"},
            ],
            max_tokens=200,
            temperature=0.3,
        )
        import re
        # Try to extract JSON from response
        json_match = re.search(r'\{[^}]+\}', resp)
        if json_match:
            parsed = json.loads(json_match.group())
            title = parsed.get("title", title)
            description = parsed.get("description", "")
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    template = ActionTemplate(
        id=str(uuid.uuid4()),
        title=title,
        description=description,
        root_prompt=action.root_prompt,
        tags="[]",
        source_action_id=action_id,
        created_at=now,
        updated_at=now,
    )
    db.add(template)
    await db.commit()
    return _template_to_response(template)
