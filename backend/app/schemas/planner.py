from pydantic import BaseModel


class PlannerTask(BaseModel):
    prompt: str
    agent_type: str
    dependencies: list[int]  # 0-based indices into the tasks list
    model: str | None = None


class PlannerOutput(BaseModel):
    tasks: list[PlannerTask]
