"""Ontology graph: typed relations between skills and domain concepts.

Inspired by oswalpalash/ontology — a typed knowledge graph for structured agent
memory. Skills can be linked to each other and to domain concepts (libraries,
APIs, data formats, error types) via typed, directed edges.

Relation types:
- depends_on: skill A requires skill B to work (e.g. "parse CSV" depends on "download data")
- supersedes: skill A replaces skill B (e.g. newer approach obsoletes old one)
- related_to: skills share context or domain (loose association)
- fixes: a correction skill fixes an error_pattern skill
- uses_tool: skill uses a specific library/API/tool (concept node)
- produces: skill produces a specific output type (concept node)
- avoids: skill avoids a specific anti-pattern (concept node)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SkillRelation(Base):
    __tablename__ = "skill_relations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    from_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    to_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    properties: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string for extra metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class SkillConcept(Base):
    """Domain concepts that skills can reference (tools, libraries, data formats, anti-patterns).

    These are the non-skill nodes in the knowledge graph — things like "scipy",
    "CSV format", "rate limiting", "arXiv API". Skills link to them via
    SkillRelation (uses_tool, produces, avoids).
    """
    __tablename__ = "skill_concepts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    concept_type: Mapped[str] = mapped_column(String(30), nullable=False)  # tool, library, api, data_format, anti_pattern, technique
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
