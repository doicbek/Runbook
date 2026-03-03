from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.task import TaskResponse


class ActionCreate(BaseModel):
    root_prompt: str = Field(..., min_length=1, max_length=50000)
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
    retry_count: int = 0
    forked_from_id: str | None = None

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
    forked_from_id: str | None = None

    model_config = {"from_attributes": True}


class PaginatedActionsResponse(BaseModel):
    actions: list[ActionListResponse]
    next_cursor: str | None = None
