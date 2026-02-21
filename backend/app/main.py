from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import async_session, engine, init_db
from app.routers import actions, artifacts, models, tasks
from app.routers import agent_definitions, planner_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session() as db:
        from app.services.agents.seed_builtins import seed_builtin_agents
        await seed_builtin_agents(db)
        from app.services.planner_config_seed import seed_planner_config
        await seed_planner_config(db)
    # Ensure artifacts directory exists
    artifacts_dir = Path(__file__).parent.parent / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    # Ensure ChromaDB persistence directory exists
    chroma_dir = Path(settings.CHROMA_PERSIST_DIR)
    chroma_dir.mkdir(parents=True, exist_ok=True)
    yield
    await engine.dispose()


app = FastAPI(title="Actions API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(actions.router)
app.include_router(tasks.router)
app.include_router(artifacts.router)
app.include_router(models.router)
app.include_router(agent_definitions.router)
app.include_router(planner_config.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
