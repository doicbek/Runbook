from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, init_db
from app.routers import actions, artifacts, tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Ensure artifacts directory exists
    artifacts_dir = Path(__file__).parent.parent / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
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


@app.get("/health")
async def health():
    return {"status": "ok"}
