from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    prompt: str
    agent_type: str = "general"
    model: str | None = None
    dependencies: list[str] = []


class TaskUpdate(BaseModel):
    prompt: str | None = None
    model: str | None = None
    agent_type: str | None = None
    dependencies: list[str] | None = None


class TaskResponse(BaseModel):
    id: str
    action_id: str
    prompt: str
    status: str
    agent_type: str
    model: str | None = None
    dependencies: list[str]
    output_summary: str | None = None
    sub_action_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskOutputResponse(BaseModel):
    id: str
    task_id: str
    artifact_ids: list[str]
    text: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactResponse(BaseModel):
    id: str
    task_id: str
    action_id: str
    type: str
    mime_type: str | None = None
    storage_path: str | None = None
    size_bytes: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LogResponse(BaseModel):
    id: str
    task_id: str
    level: str
    message: str
    timestamp: datetime
    structured: dict | None = None

    model_config = {"from_attributes": True}
