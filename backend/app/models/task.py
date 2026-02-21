import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    action_id: Mapped[str] = mapped_column(String(36), ForeignKey("actions.id"), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, running, completed, failed
    agent_type: Mapped[str] = mapped_column(String(50), default="general")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dependencies: Mapped[list] = mapped_column(JSON, default=list)  # array of task IDs
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    action: Mapped["Action"] = relationship("Action", back_populates="tasks")  # noqa: F821
    outputs: Mapped[list["TaskOutput"]] = relationship("TaskOutput", back_populates="task", cascade="all, delete-orphan")  # noqa: F821
    artifacts: Mapped[list["Artifact"]] = relationship("Artifact", back_populates="task", cascade="all, delete-orphan")  # noqa: F821
    logs: Mapped[list["Log"]] = relationship("Log", back_populates="task", cascade="all, delete-orphan")  # noqa: F821
