from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_skill import AgentSkill
from app.schemas.agent_skill import (
    AgentSkillCreate,
    AgentSkillResponse,
    AgentSkillUpdate,
)

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[AgentSkillResponse])
async def list_skills(
    agent_type: str | None = None,
    category: str | None = None,
    source: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(AgentSkill).order_by(AgentSkill.last_seen.desc())
    if agent_type:
        query = query.where(AgentSkill.agent_type == agent_type)
    if category:
        query = query.where(AgentSkill.category == category)
    if source:
        query = query.where(AgentSkill.source == source)
    if status:
        query = query.where(AgentSkill.status == status)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/stats")
async def skill_stats(db: AsyncSession = Depends(get_db)):
    """Aggregate stats for the skills dashboard."""
    result = await db.execute(select(AgentSkill))
    skills = list(result.scalars().all())
    by_category: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_source: dict[str, int] = {}
    promoted = 0
    pending_high = 0
    for s in skills:
        by_category[s.category] = by_category.get(s.category, 0) + 1
        by_priority[s.priority] = by_priority.get(s.priority, 0) + 1
        by_source[s.source] = by_source.get(s.source, 0) + 1
        if s.status == "promoted":
            promoted += 1
        if s.status == "pending" and s.priority in ("high", "critical"):
            pending_high += 1
    return {
        "total": len(skills),
        "by_category": by_category,
        "by_priority": by_priority,
        "by_source": by_source,
        "promoted": promoted,
        "pending_high_priority": pending_high,
    }


@router.get("/{skill_id}", response_model=AgentSkillResponse)
async def get_skill(skill_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentSkill).where(AgentSkill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.post("", response_model=AgentSkillResponse, status_code=201)
async def create_skill(body: AgentSkillCreate, db: AsyncSession = Depends(get_db)):
    skill = AgentSkill(
        agent_type=body.agent_type,
        title=body.title,
        description=body.description,
        source=body.source,
        category=body.category,
        priority=body.priority,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


@router.patch("/{skill_id}", response_model=AgentSkillResponse)
async def update_skill(
    skill_id: str,
    body: AgentSkillUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AgentSkill).where(AgentSkill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    if body.title is not None:
        skill.title = body.title
    if body.description is not None:
        skill.description = body.description
    if body.is_active is not None:
        skill.is_active = body.is_active
    if body.priority is not None:
        skill.priority = body.priority
    if body.status is not None:
        skill.status = body.status
    if body.category is not None:
        skill.category = body.category

    await db.commit()
    await db.refresh(skill)
    return skill


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentSkill).where(AgentSkill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    await db.delete(skill)
    await db.commit()
