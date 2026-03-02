from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_memory_model import AgentMemory, AgentMemoryVersion

router = APIRouter(prefix="/agent-memory", tags=["agent-memory"])


class AgentMemoryListItem(BaseModel):
    agent_type: str
    content_preview: str
    version: int
    updated_at: datetime


class AgentMemoryDetail(BaseModel):
    agent_type: str
    content: str
    version: int
    updated_at: datetime
    created_at: datetime


class AgentMemoryUpdate(BaseModel):
    content: str


class AgentMemoryVersionItem(BaseModel):
    version: int
    created_at: datetime


class AgentMemoryVersionDetail(BaseModel):
    version: int
    content: str
    created_at: datetime


@router.get("", response_model=list[AgentMemoryListItem])
async def list_agent_memories(db: AsyncSession = Depends(get_db)):
    """List all agent memories with truncated content."""
    result = await db.execute(
        select(AgentMemory).order_by(AgentMemory.updated_at.desc())
    )
    memories = result.scalars().all()
    return [
        AgentMemoryListItem(
            agent_type=m.agent_type,
            content_preview=m.content[:200] if m.content else "",
            version=m.version,
            updated_at=m.updated_at,
        )
        for m in memories
    ]


@router.get("/{agent_type}", response_model=AgentMemoryDetail)
async def get_agent_memory(agent_type: str, db: AsyncSession = Depends(get_db)):
    """Get full memory content for an agent type."""
    result = await db.execute(
        select(AgentMemory).where(AgentMemory.agent_type == agent_type)
    )
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail=f"No memory found for agent type '{agent_type}'")
    return AgentMemoryDetail(
        agent_type=memory.agent_type,
        content=memory.content,
        version=memory.version,
        updated_at=memory.updated_at,
        created_at=memory.created_at,
    )


@router.patch("/{agent_type}", response_model=AgentMemoryDetail)
async def update_agent_memory(
    agent_type: str,
    body: AgentMemoryUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update memory content, creating a version snapshot."""
    import uuid
    from datetime import timezone

    result = await db.execute(
        select(AgentMemory).where(AgentMemory.agent_type == agent_type)
    )
    memory = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if memory:
        memory.content = body.content
        memory.version += 1
        memory.updated_at = now
    else:
        memory = AgentMemory(
            id=str(uuid.uuid4()),
            agent_type=agent_type,
            content=body.content,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(memory)

    # Create version snapshot
    version_row = AgentMemoryVersion(
        id=str(uuid.uuid4()),
        memory_id=memory.id,
        content=body.content,
        version=memory.version,
        created_at=now,
    )
    db.add(version_row)
    await db.commit()

    return AgentMemoryDetail(
        agent_type=memory.agent_type,
        content=memory.content,
        version=memory.version,
        updated_at=memory.updated_at,
        created_at=memory.created_at,
    )


@router.get("/{agent_type}/versions", response_model=list[AgentMemoryVersionItem])
async def list_memory_versions(agent_type: str, db: AsyncSession = Depends(get_db)):
    """List version history for an agent type's memory."""
    # First verify the memory exists
    result = await db.execute(
        select(AgentMemory).where(AgentMemory.agent_type == agent_type)
    )
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail=f"No memory found for agent type '{agent_type}'")

    result = await db.execute(
        select(AgentMemoryVersion)
        .where(AgentMemoryVersion.memory_id == memory.id)
        .order_by(AgentMemoryVersion.version.desc())
    )
    versions = result.scalars().all()
    return [
        AgentMemoryVersionItem(version=v.version, created_at=v.created_at)
        for v in versions
    ]


@router.get("/{agent_type}/versions/{version}", response_model=AgentMemoryVersionDetail)
async def get_memory_version(
    agent_type: str,
    version: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific version of an agent type's memory."""
    result = await db.execute(
        select(AgentMemory).where(AgentMemory.agent_type == agent_type)
    )
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail=f"No memory found for agent type '{agent_type}'")

    result = await db.execute(
        select(AgentMemoryVersion).where(
            AgentMemoryVersion.memory_id == memory.id,
            AgentMemoryVersion.version == version,
        )
    )
    ver = result.scalar_one_or_none()
    if not ver:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")

    return AgentMemoryVersionDetail(
        version=ver.version,
        content=ver.content,
        created_at=ver.created_at,
    )
