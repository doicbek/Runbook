import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentIteration(Base):
    __tablename__ = "agent_iterations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False)
    action_id: Mapped[str] = mapped_column(String(36), ForeignKey("actions.id"), nullable=False)
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based
    loop_type: Mapped[str] = mapped_column(String(20), default="primary")  # primary, retry
    attempt_number: Mapped[int] = mapped_column(Integer, default=0)  # 0 for primary, 1+ for retries
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list)  # [{tool, input, output, duration_ms, success}]
    outcome: Mapped[str] = mapped_column(
        String(30), default="continue"
    )  # continue, completed, failed, paused, user_redirected, user_guidance
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    lessons_learned: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_agent_iterations_task_iteration", "task_id", "iteration_number"),
    )
