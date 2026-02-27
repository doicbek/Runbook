"""Background service that prunes old AgentIteration records to prevent unbounded DB growth."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.config import settings
from app.database import async_session
from app.models.action import Action
from app.models.agent_iteration import AgentIteration

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours


async def cleanup_old_iterations() -> int:
    """Delete AgentIteration records older than retention period for completed actions.

    Returns the number of deleted records.
    """
    retention_days = settings.ITERATION_RETENTION_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    async with async_session() as db:
        # Find completed action IDs
        completed_action_ids_result = await db.execute(
            select(Action.id).where(Action.status == "completed")
        )
        completed_action_ids = [row[0] for row in completed_action_ids_result.all()]

        if not completed_action_ids:
            return 0

        # Delete old iterations belonging to completed actions
        result = await db.execute(
            delete(AgentIteration).where(
                AgentIteration.action_id.in_(completed_action_ids),
                AgentIteration.created_at < cutoff,
            )
        )
        await db.commit()

        deleted = result.rowcount  # type: ignore[union-attr]
        if deleted:
            logger.info(
                "Cleaned up %d iteration records older than %d days",
                deleted,
                retention_days,
            )
        return deleted


async def iteration_cleanup_loop() -> None:
    """Background loop that runs cleanup on startup and every 24 hours."""
    while True:
        try:
            await cleanup_old_iterations()
        except Exception:
            logger.exception("Error during iteration cleanup")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
