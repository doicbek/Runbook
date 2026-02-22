from datetime import datetime

from pydantic import BaseModel

from app.schemas.task import TaskResponse


class ActionCreate(BaseModel):
    root_prompt: str
    title: str | None = None


class ActionUpdate(BaseModel):
    title: str | None = None
    root_prompt: str | None = None


class ActionResponse(BaseModel):
    id: str
    title: str
    root_prompt: str
    status: str
    created_at: datetime
    updated_at: datetime
    tasks: list[TaskResponse] = []
    parent_action_id: str | None = None
    parent_task_id: str | None = None
    output_contract: str | None = None
    depth: int = 0

    model_config = {"from_attributes": True}


class ActionListResponse(BaseModel):
    id: str
    title: str
    root_prompt: str
    status: str
    created_at: datetime
    updated_at: datetime
    task_count: int = 0
    parent_action_id: str | None = None
    depth: int = 0

    model_config = {"from_attributes": True}
