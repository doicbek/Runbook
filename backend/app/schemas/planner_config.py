from datetime import datetime

from pydantic import BaseModel


class PlannerConfigResponse(BaseModel):
    id: str
    system_prompt: str
    model: str
    max_tasks: int
    max_retries: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlannerConfigUpdate(BaseModel):
    system_prompt: str | None = None
    model: str | None = None
    max_tasks: int | None = None
    max_retries: int | None = None


class PlannerPreviewRequest(BaseModel):
    prompt: str
    system_prompt: str | None = None  # if set, use this instead of DB config


class PlannerPreviewTask(BaseModel):
    prompt: str
    agent_type: str
    dependencies: list[int]
    model: str | None = None


class PlannerPreviewResponse(BaseModel):
    tasks: list[PlannerPreviewTask]
    used_system_prompt: str


class ModifyPromptRequest(BaseModel):
    instruction: str
    current_prompt: str | None = None  # if omitted, loads from DB
    model: str | None = None


class ModifyPromptResponse(BaseModel):
    system_prompt: str


class ApiKeyStatus(BaseModel):
    provider: str
    configured: bool
    models: list[str]
