import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.planner_config import PlannerConfig
from app.services.planner import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def seed_planner_config(db: AsyncSession) -> None:
    """Idempotent — only inserts if the row doesn't exist yet."""
    result = await db.execute(select(PlannerConfig).where(PlannerConfig.id == "default"))
    if result.scalar_one_or_none() is None:
        cfg = PlannerConfig(
            id="default",
            system_prompt=SYSTEM_PROMPT,
            model=settings.OPENAI_MODEL,
            max_tasks=8,
            max_retries=2,
        )
        db.add(cfg)
        await db.commit()
        logger.info("Planner config seeded with defaults.")
    else:
        logger.info("Planner config already exists, skipping seed.")
