"""Per-agent persistent memory: lessons learned from failures.

Memory is stored in the AgentMemory/AgentMemoryVersion DB tables and injected
into the task prompt at runtime so agents can avoid repeating past mistakes.
"""

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MEMORY_DIR = Path(__file__).parent.parent.parent.parent / "data" / "agent_memory"


async def load_memory(agent_type: str, db: AsyncSession) -> str:
    """Return the agent's current memory/lessons from DB. Empty string if none."""
    from app.models.agent_memory_model import AgentMemory

    result = await db.execute(
        select(AgentMemory).where(AgentMemory.agent_type == agent_type)
    )
    memory = result.scalar_one_or_none()
    if memory and memory.content:
        return memory.content.strip()
    return ""


async def save_memory(agent_type: str, content: str, db: AsyncSession) -> None:
    """Upsert the agent's memory row and create a version snapshot."""
    import uuid
    from datetime import datetime, timezone

    from app.models.agent_memory_model import AgentMemory, AgentMemoryVersion

    result = await db.execute(
        select(AgentMemory).where(AgentMemory.agent_type == agent_type)
    )
    memory = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if memory:
        memory.content = content
        memory.version += 1
        memory.updated_at = now
    else:
        memory = AgentMemory(
            id=str(uuid.uuid4()),
            agent_type=agent_type,
            content=content,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(memory)

    # Create version snapshot
    version_row = AgentMemoryVersion(
        id=str(uuid.uuid4()),
        memory_id=memory.id,
        content=content,
        version=memory.version,
        created_at=now,
    )
    db.add(version_row)
    await db.commit()
    logger.info(f"[AgentMemory] Saved lesson for {agent_type} (v{memory.version})")


async def generate_and_save_lesson(
    agent_type: str,
    task_prompt: str,
    error: str,
    db: AsyncSession,
) -> None:
    """Call a fast LLM to generate/revise a lesson from a failure and persist it."""
    from app.services.llm_client import utility_completion

    existing = await load_memory(agent_type, db)
    existing_block = (
        f"\n\nExisting lessons to revise (update or expand as needed):\n{existing}"
        if existing
        else ""
    )

    try:
        lesson = await utility_completion(
            [
                {
                    "role": "system",
                    "content": (
                        f"You are a memory assistant for a `{agent_type}` AI agent. "
                        "Your job is to write concise, actionable lessons that help the agent "
                        "avoid repeating failures. Write in markdown, 1–3 bullet points maximum. "
                        "Be specific about what to do differently, not just what went wrong."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"The agent failed on this task: {task_prompt[:300]}\n"
                        f"Error: {error[:500]}"
                        f"{existing_block}\n\n"
                        "Write (or revise) a concise lesson for this agent to remember."
                    ),
                },
            ],
            max_tokens=200,
            temperature=0.3,
        )
        await save_memory(agent_type, lesson.strip(), db)
    except Exception:
        logger.exception(f"[AgentMemory] Failed to generate lesson for {agent_type}")


async def seed_memory_from_files(db: AsyncSession) -> None:
    """On startup, seed DB from existing markdown files if no DB record exists."""
    from app.models.agent_memory_model import AgentMemory

    if not MEMORY_DIR.exists():
        return

    for md_file in MEMORY_DIR.glob("*.md"):
        agent_type = md_file.stem
        content = md_file.read_text(encoding="utf-8").strip()
        if not content:
            continue

        result = await db.execute(
            select(AgentMemory).where(AgentMemory.agent_type == agent_type)
        )
        existing = result.scalar_one_or_none()
        if existing:
            continue  # DB already has a record, skip

        import uuid
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        memory = AgentMemory(
            id=str(uuid.uuid4()),
            agent_type=agent_type,
            content=content,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(memory)
        logger.info(f"[AgentMemory] Seeded DB from file for {agent_type}")

    await db.commit()
