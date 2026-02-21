from fastapi import APIRouter

from app.services.llm_client import (
    DEFAULT_MODELS_BY_AGENT_TYPE,
    get_available_models,
)

router = APIRouter(tags=["models"])


@router.get("/models")
async def list_models():
    """Return available models (those with configured API keys) and default assignments."""
    return {
        "models": get_available_models(),
        "defaults_by_agent_type": DEFAULT_MODELS_BY_AGENT_TYPE,
    }
