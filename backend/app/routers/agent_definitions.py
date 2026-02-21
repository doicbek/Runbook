import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_definition import AgentDefinition
from app.schemas.agent_definition import (
    AgentDefinitionCreate,
    AgentDefinitionResponse,
    AgentDefinitionUpdate,
    ModifyRequest,
    ModifyResponse,
    ScaffoldRequest,
    ScaffoldResponse,
)
from app.services.agents.tool_catalog import TOOL_CATALOG

router = APIRouter(prefix="/agent-definitions", tags=["agent-definitions"])

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _validate_slug(agent_type: str) -> None:
    if not _SLUG_RE.match(agent_type):
        raise HTTPException(
            status_code=422,
            detail="agent_type must match ^[a-z][a-z0-9_]*$ (lowercase letters, digits, underscores, starting with a letter)",
        )


@router.get("", response_model=list[AgentDefinitionResponse])
async def list_agent_definitions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentDefinition).order_by(
            AgentDefinition.is_builtin.desc(),
            AgentDefinition.name.asc(),
        )
    )
    return result.scalars().all()


@router.get("/tools")
async def list_tools():
    return TOOL_CATALOG


@router.get("/{agent_id}", response_model=AgentDefinitionResponse)
async def get_agent_definition(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentDefinition).where(AgentDefinition.id == agent_id)
    )
    defn = result.scalar_one_or_none()
    if not defn:
        raise HTTPException(status_code=404, detail="Agent definition not found")
    return defn


@router.post("", response_model=AgentDefinitionResponse, status_code=201)
async def create_agent_definition(
    body: AgentDefinitionCreate,
    db: AsyncSession = Depends(get_db),
):
    _validate_slug(body.agent_type)

    # Check uniqueness
    result = await db.execute(
        select(AgentDefinition).where(AgentDefinition.agent_type == body.agent_type)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Agent type '{body.agent_type}' already exists")

    defn = AgentDefinition(
        agent_type=body.agent_type,
        name=body.name,
        description=body.description,
        code=body.code,
        tools=body.tools,
        requirements=body.requirements,
        setup_notes=body.setup_notes,
        mcp_config=body.mcp_config,
        status=body.status,
        is_builtin=False,
        icon=body.icon,
    )
    db.add(defn)
    await db.commit()
    await db.refresh(defn)
    return defn


@router.patch("/{agent_id}", response_model=AgentDefinitionResponse)
async def update_agent_definition(
    agent_id: str,
    body: AgentDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentDefinition).where(AgentDefinition.id == agent_id)
    )
    defn = result.scalar_one_or_none()
    if not defn:
        raise HTTPException(status_code=404, detail="Agent definition not found")
    # is_builtin and agent_type are immutable — everything else is editable

    if body.name is not None:
        defn.name = body.name
    if body.description is not None:
        defn.description = body.description
    if body.code is not None:
        defn.code = body.code
    if body.tools is not None:
        defn.tools = body.tools
    if body.requirements is not None:
        defn.requirements = body.requirements
    if body.setup_notes is not None:
        defn.setup_notes = body.setup_notes
    if body.mcp_config is not None:
        defn.mcp_config = body.mcp_config
    if body.status is not None:
        defn.status = body.status
    if body.icon is not None:
        defn.icon = body.icon

    await db.commit()
    await db.refresh(defn)
    return defn


@router.delete("/{agent_id}", status_code=204)
async def delete_agent_definition(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentDefinition).where(AgentDefinition.id == agent_id)
    )
    defn = result.scalar_one_or_none()
    if not defn:
        raise HTTPException(status_code=404, detail="Agent definition not found")
    if defn.is_builtin:
        raise HTTPException(status_code=403, detail="Cannot delete a built-in agent")

    await db.delete(defn)
    await db.commit()


@router.post("/scaffold", response_model=ScaffoldResponse)
async def scaffold_agent(body: ScaffoldRequest):
    from app.services.agents.scaffolding_service import AgentScaffoldingService

    service = AgentScaffoldingService()
    return await service.scaffold(
        name=body.name,
        description=body.description,
        tools=body.tools,
        model=body.model,
    )


@router.post("/{agent_id}/modify", response_model=ModifyResponse)
async def modify_agent(
    agent_id: str,
    body: ModifyRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentDefinition).where(AgentDefinition.id == agent_id)
    )
    defn = result.scalar_one_or_none()
    if not defn:
        raise HTTPException(status_code=404, detail="Agent definition not found")

    from app.services.agents.scaffolding_service import AgentScaffoldingService

    service = AgentScaffoldingService()
    current_code = body.current_code if body.current_code is not None else defn.code
    code = await service.modify(
        name=defn.name,
        description=defn.description,
        current_code=current_code,
        modification_prompt=body.prompt,
        model=body.model,
    )
    return ModifyResponse(code=code)
