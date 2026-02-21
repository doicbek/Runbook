from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlannerConfig(Base):
    __tablename__ = "planner_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="gpt-4o")
    max_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
