from datetime import datetime

from pydantic import BaseModel


class AgentSkillCreate(BaseModel):
    agent_type: str
    title: str
    description: str
    source: str = "manual"
    category: str = "learning"  # learning, error_pattern, correction, best_practice
    priority: str = "medium"  # low, medium, high, critical


class AgentSkillUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    is_active: bool | None = None
    priority: str | None = None
    status: str | None = None
    category: str | None = None


class AgentSkillResponse(BaseModel):
    id: str
    agent_type: str
    title: str
    description: str
    source: str
    source_task_id: str | None = None
    source_action_id: str | None = None
    is_active: bool
    usage_count: int
    category: str
    priority: str
    status: str
    pattern_key: str | None = None
    recurrence_count: int
    first_seen: datetime
    last_seen: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
