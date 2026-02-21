import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentDefinition(Base):
    __tablename__ = "agent_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_type: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    setup_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    mcp_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft, active, error
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    icon: Mapped[str] = mapped_column(String(50), default="🤖")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
