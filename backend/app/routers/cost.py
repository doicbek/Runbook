from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Action, LLMUsage, Task

router = APIRouter(tags=["cost"])


@router.get("/actions/{action_id}/cost")
async def get_action_cost(action_id: str, db: AsyncSession = Depends(get_db)):
    """Get cost breakdown for a specific action."""
    result = await db.execute(select(Action).where(Action.id == action_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Action not found")

    # Total cost
    total_result = await db.execute(
        select(func.coalesce(func.sum(LLMUsage.cost_usd), 0.0)).where(
            LLMUsage.action_id == action_id
        )
    )
    total_cost_usd = float(total_result.scalar_one())

    # By task
    by_task_result = await db.execute(
        select(
            LLMUsage.task_id,
            func.sum(LLMUsage.cost_usd).label("cost_usd"),
        )
        .where(LLMUsage.action_id == action_id, LLMUsage.task_id.isnot(None))
        .group_by(LLMUsage.task_id)
    )
    by_task = [
        {"task_id": row.task_id, "cost_usd": round(float(row.cost_usd), 6)}
        for row in by_task_result.all()
    ]

    # By model
    by_model_result = await db.execute(
        select(
            LLMUsage.model,
            func.sum(LLMUsage.cost_usd).label("cost_usd"),
            func.count().label("calls"),
        )
        .where(LLMUsage.action_id == action_id)
        .group_by(LLMUsage.model)
    )
    by_model = [
        {
            "model": row.model,
            "cost_usd": round(float(row.cost_usd), 6),
            "calls": row.calls,
        }
        for row in by_model_result.all()
    ]

    return {
        "total_cost_usd": round(total_cost_usd, 6),
        "by_task": by_task,
        "by_model": by_model,
    }


@router.get("/cost/summary")
async def get_cost_summary(db: AsyncSession = Depends(get_db)):
    """Get aggregate cost summary across all actions."""
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    # Total cost
    total_result = await db.execute(
        select(func.coalesce(func.sum(LLMUsage.cost_usd), 0.0))
    )
    total_cost_usd = float(total_result.scalar_one())

    # Last 7 days
    last_7d_result = await db.execute(
        select(func.coalesce(func.sum(LLMUsage.cost_usd), 0.0)).where(
            LLMUsage.created_at >= seven_days_ago
        )
    )
    last_7d_cost = float(last_7d_result.scalar_one())

    # Last 30 days
    last_30d_result = await db.execute(
        select(func.coalesce(func.sum(LLMUsage.cost_usd), 0.0)).where(
            LLMUsage.created_at >= thirty_days_ago
        )
    )
    last_30d_cost = float(last_30d_result.scalar_one())

    # By model
    by_model_result = await db.execute(
        select(
            LLMUsage.model,
            func.sum(LLMUsage.cost_usd).label("cost_usd"),
            func.count().label("calls"),
        ).group_by(LLMUsage.model)
    )
    by_model = [
        {
            "model": row.model,
            "cost_usd": round(float(row.cost_usd), 6),
            "calls": row.calls,
        }
        for row in by_model_result.all()
    ]

    # By agent type (join via task)
    by_agent_result = await db.execute(
        select(
            Task.agent_type,
            func.sum(LLMUsage.cost_usd).label("cost_usd"),
            func.count().label("calls"),
        )
        .join(Task, LLMUsage.task_id == Task.id)
        .group_by(Task.agent_type)
    )
    by_agent_type = [
        {
            "agent_type": row.agent_type,
            "cost_usd": round(float(row.cost_usd), 6),
            "calls": row.calls,
        }
        for row in by_agent_result.all()
    ]

    return {
        "total_cost_usd": round(total_cost_usd, 6),
        "by_model": by_model,
        "by_agent_type": by_agent_type,
        "last_7d_cost": round(last_7d_cost, 6),
        "last_30d_cost": round(last_30d_cost, 6),
    }
