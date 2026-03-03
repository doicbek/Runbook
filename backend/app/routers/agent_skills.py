import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_skill import AgentSkill
from app.models.skill_relation import SkillConcept, SkillRelation
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
    # Bulk delete any relations referencing this skill
    from sqlalchemy import delete as sa_delete
    await db.execute(
        sa_delete(SkillRelation).where(
            or_(SkillRelation.from_id == skill_id, SkillRelation.to_id == skill_id)
        )
    )
    await db.delete(skill)
    await db.commit()


# ── Ontology: Concepts ──────────────────────────────────────────────────────


class ConceptCreate(BaseModel):
    name: str
    concept_type: str  # tool, library, api, data_format, anti_pattern, technique
    description: str | None = None


class ConceptResponse(BaseModel):
    id: str
    name: str
    concept_type: str
    description: str | None
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/ontology/concepts")
async def list_concepts(
    concept_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(SkillConcept).order_by(SkillConcept.name)
    if concept_type:
        query = query.where(SkillConcept.concept_type == concept_type)
    result = await db.execute(query)
    return [
        {
            "id": c.id,
            "name": c.name,
            "concept_type": c.concept_type,
            "description": c.description,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in result.scalars().all()
    ]


@router.post("/ontology/concepts", status_code=201)
async def create_concept(body: ConceptCreate, db: AsyncSession = Depends(get_db)):
    # Upsert: if concept with same name exists, return it with 200
    result = await db.execute(
        select(SkillConcept).where(SkillConcept.name == body.name)
    )
    existing = result.scalar_one_or_none()
    if existing:
        from starlette.responses import JSONResponse
        return JSONResponse(
            status_code=200,
            content={
                "id": existing.id, "name": existing.name,
                "concept_type": existing.concept_type,
                "description": existing.description,
                "created_at": existing.created_at.isoformat() if existing.created_at else None,
                "note": "Concept already exists",
            },
        )

    concept = SkillConcept(
        name=body.name,
        concept_type=body.concept_type,
        description=body.description,
    )
    db.add(concept)
    await db.commit()
    await db.refresh(concept)
    return {
        "id": concept.id, "name": concept.name,
        "concept_type": concept.concept_type,
        "description": concept.description,
        "created_at": concept.created_at.isoformat() if concept.created_at else None,
    }


@router.delete("/ontology/concepts/{concept_id}", status_code=204)
async def delete_concept(concept_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SkillConcept).where(SkillConcept.id == concept_id))
    concept = result.scalar_one_or_none()
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")
    # Clean up relations
    for rel in (await db.execute(
        select(SkillRelation).where(
            or_(SkillRelation.from_id == concept_id, SkillRelation.to_id == concept_id)
        )
    )).scalars().all():
        await db.delete(rel)
    await db.delete(concept)
    await db.commit()


# ── Ontology: Relations ─────────────────────────────────────────────────────

VALID_RELATION_TYPES = {
    "depends_on", "supersedes", "related_to", "fixes",
    "uses_tool", "produces", "avoids",
}


class RelationCreate(BaseModel):
    from_id: str
    relation_type: str
    to_id: str
    properties: dict | None = None


class RelationResponse(BaseModel):
    id: str
    from_id: str
    relation_type: str
    to_id: str
    properties: dict | None
    created_at: str


@router.get("/ontology/relations")
async def list_relations(
    node_id: str | None = None,
    relation_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(SkillRelation)
    if node_id:
        query = query.where(
            or_(SkillRelation.from_id == node_id, SkillRelation.to_id == node_id)
        )
    if relation_type:
        query = query.where(SkillRelation.relation_type == relation_type)
    result = await db.execute(query)
    return [
        {
            "id": r.id,
            "from_id": r.from_id,
            "relation_type": r.relation_type,
            "to_id": r.to_id,
            "properties": json.loads(r.properties) if r.properties else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in result.scalars().all()
    ]


@router.post("/ontology/relations", status_code=201)
async def create_relation(body: RelationCreate, db: AsyncSession = Depends(get_db)):
    if body.relation_type not in VALID_RELATION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid relation_type. Must be one of: {', '.join(sorted(VALID_RELATION_TYPES))}",
        )

    # Prevent duplicate relations
    result = await db.execute(
        select(SkillRelation).where(
            SkillRelation.from_id == body.from_id,
            SkillRelation.relation_type == body.relation_type,
            SkillRelation.to_id == body.to_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Relation already exists")

    # Prevent self-loops
    if body.from_id == body.to_id:
        raise HTTPException(status_code=422, detail="Self-loops are not allowed")

    rel = SkillRelation(
        from_id=body.from_id,
        relation_type=body.relation_type,
        to_id=body.to_id,
        properties=json.dumps(body.properties) if body.properties else None,
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return {
        "id": rel.id,
        "from_id": rel.from_id,
        "relation_type": rel.relation_type,
        "to_id": rel.to_id,
        "properties": body.properties,
        "created_at": rel.created_at.isoformat() if rel.created_at else None,
    }


@router.delete("/ontology/relations/{relation_id}", status_code=204)
async def delete_relation(relation_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SkillRelation).where(SkillRelation.id == relation_id))
    rel = result.scalar_one_or_none()
    if not rel:
        raise HTTPException(status_code=404, detail="Relation not found")
    await db.delete(rel)
    await db.commit()


# ── Ontology: Graph view ────────────────────────────────────────────────────


@router.get("/ontology/graph")
async def get_ontology_graph(
    agent_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return the full ontology graph as nodes + edges for visualization."""
    # Fetch skills
    skill_query = select(AgentSkill)
    if agent_type:
        skill_query = skill_query.where(AgentSkill.agent_type == agent_type)
    skills = (await db.execute(skill_query)).scalars().all()
    skill_ids = {s.id for s in skills}

    # Fetch concepts
    concepts = (await db.execute(select(SkillConcept))).scalars().all()
    concept_ids = {c.id for c in concepts}

    all_ids = skill_ids | concept_ids

    # Fetch relations where at least one end is in our node set
    relations = (await db.execute(
        select(SkillRelation).where(
            or_(
                SkillRelation.from_id.in_(all_ids),
                SkillRelation.to_id.in_(all_ids),
            )
        )
    )).scalars().all()

    nodes = []
    for s in skills:
        nodes.append({
            "id": s.id,
            "type": "skill",
            "label": s.title,
            "agent_type": s.agent_type,
            "category": s.category,
            "priority": s.priority,
            "status": s.status,
            "recurrence_count": s.recurrence_count,
        })
    for c in concepts:
        nodes.append({
            "id": c.id,
            "type": "concept",
            "label": c.name,
            "concept_type": c.concept_type,
        })

    edges = [
        {
            "id": r.id,
            "from_id": r.from_id,
            "relation_type": r.relation_type,
            "to_id": r.to_id,
            "properties": json.loads(r.properties) if r.properties else None,
        }
        for r in relations
    ]

    return {"nodes": nodes, "edges": edges}
