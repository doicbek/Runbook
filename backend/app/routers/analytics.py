from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case, cast, Float
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ToolUsage

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/tools")
async def get_tool_analytics(
    agent_type: str | None = Query(None),
    days: int | None = Query(None, description="Filter to last N days"),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate tool usage stats, optionally filtered by agent_type and time range."""
    conditions = []
    if agent_type:
        conditions.append(ToolUsage.agent_type == agent_type)
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        conditions.append(ToolUsage.created_at >= cutoff)

    stmt = (
        select(
            ToolUsage.tool_name,
            func.count().label("total_calls"),
            cast(
                func.sum(case((ToolUsage.success == True, 1), else_=0)) * 100.0  # noqa: E712
                / func.count(),
                Float,
            ).label("success_rate"),
            func.avg(ToolUsage.duration_ms).label("avg_duration_ms"),
            func.group_concat(ToolUsage.agent_type.distinct()).label("agent_types_csv"),
        )
        .where(*conditions)
        .group_by(ToolUsage.tool_name)
        .order_by(func.count().desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "tool_name": row.tool_name,
            "total_calls": row.total_calls,
            "success_rate": round(float(row.success_rate), 1) if row.success_rate is not None else 0.0,
            "avg_duration_ms": round(float(row.avg_duration_ms)) if row.avg_duration_ms is not None else 0,
            "agent_types": row.agent_types_csv.split(",") if row.agent_types_csv else [],
        }
        for row in rows
    ]


@router.get("/agents/{agent_type}/tools")
async def get_agent_tool_analytics(
    agent_type: str,
    days: int | None = Query(None, description="Filter to last N days"),
    db: AsyncSession = Depends(get_db),
):
    """Tool usage breakdown for a specific agent type."""
    conditions = [ToolUsage.agent_type == agent_type]
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        conditions.append(ToolUsage.created_at >= cutoff)

    stmt = (
        select(
            ToolUsage.tool_name,
            func.count().label("total_calls"),
            cast(
                func.sum(case((ToolUsage.success == True, 1), else_=0)) * 100.0  # noqa: E712
                / func.count(),
                Float,
            ).label("success_rate"),
            func.avg(ToolUsage.duration_ms).label("avg_duration_ms"),
        )
        .where(*conditions)
        .group_by(ToolUsage.tool_name)
        .order_by(func.count().desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "tool_name": row.tool_name,
            "total_calls": row.total_calls,
            "success_rate": round(float(row.success_rate), 1) if row.success_rate is not None else 0.0,
            "avg_duration_ms": round(float(row.avg_duration_ms)) if row.avg_duration_ms is not None else 0,
        }
        for row in rows
    ]
