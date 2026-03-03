from datetime import datetime

from pydantic import BaseModel, Field


class AvailableModel(BaseModel):
    name: str
    display_name: str
    provider: str


class PlannerConfigResponse(BaseModel):
    id: str
    system_prompt: str
    model: str
    max_tasks: int
    max_retries: int
    updated_at: datetime
    available_models: list[AvailableModel] = []

    model_config = {"from_attributes": True}


class PlannerConfigUpdate(BaseModel):
    system_prompt: str | None = None
    model: str | None = None
    max_tasks: int | None = Field(None, ge=1, le=50)
    max_retries: int | None = Field(None, ge=0, le=10)


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
