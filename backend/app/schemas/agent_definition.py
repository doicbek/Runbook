from datetime import datetime

from pydantic import BaseModel


class AgentDefinitionCreate(BaseModel):
    agent_type: str
    name: str
    description: str = ""
    code: str | None = None
    tools: list[str] = []
    requirements: str | None = None
    setup_notes: str | None = None
    mcp_config: dict | None = None
    status: str = "active"
    icon: str = "🤖"


class AgentDefinitionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    code: str | None = None
    tools: list[str] | None = None
    requirements: str | None = None
    setup_notes: str | None = None
    mcp_config: dict | None = None
    status: str | None = None
    icon: str | None = None


class AgentDefinitionResponse(BaseModel):
    id: str
    agent_type: str
    name: str
    description: str
    code: str | None = None
    tools: list[str]
    requirements: str | None = None
    setup_notes: str | None = None
    mcp_config: dict | None = None
    status: str
    is_builtin: bool
    icon: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScaffoldRequest(BaseModel):
    name: str
    description: str
    tools: list[str]
    model: str | None = None


class ScaffoldResponse(BaseModel):
    code: str
    requirements: str
    setup_notes: str


class ModifyRequest(BaseModel):
    prompt: str
    current_code: str | None = None  # if omitted, backend loads from DB
    model: str | None = None


class ModifyResponse(BaseModel):
    code: str
