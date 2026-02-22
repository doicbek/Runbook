from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False, "timeout": 30},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    from app.models import action, agent_definition, artifact, log, planner_config, task, task_output  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Idempotent column migrations for existing DBs
    async with engine.begin() as conn:
        for stmt in [
            "ALTER TABLE actions ADD COLUMN parent_action_id TEXT",
            "ALTER TABLE actions ADD COLUMN parent_task_id TEXT",
            "ALTER TABLE actions ADD COLUMN output_contract TEXT",
            "ALTER TABLE actions ADD COLUMN depth INTEGER DEFAULT 0",
            "ALTER TABLE tasks ADD COLUMN sub_action_id TEXT",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # column already exists

    # Enable WAL mode for better concurrency
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
        await conn.commit()


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session
