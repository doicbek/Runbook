import logging

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.planner_config import PlannerConfig
from app.schemas.planner_config import (
    ApiKeyStatus,
    ModifyPromptRequest,
    ModifyPromptResponse,
    PlannerConfigResponse,
    PlannerConfigUpdate,
    PlannerPreviewRequest,
    PlannerPreviewResponse,
    PlannerPreviewTask,
)
from app.services.llm_client import MODEL_REGISTRY, chat_completion, get_default_model_for_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/planner-config", tags=["planner-config"])


async def _get_config(db: AsyncSession) -> PlannerConfig:
    result = await db.execute(select(PlannerConfig).where(PlannerConfig.id == "default"))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=500, detail="Planner config not initialised")
    return cfg


@router.get("", response_model=PlannerConfigResponse)
async def get_planner_config(db: AsyncSession = Depends(get_db)):
    return await _get_config(db)


@router.get("/api-status", response_model=list[ApiKeyStatus])
async def get_api_status():
    """Return which API providers are configured."""
    provider_keys: dict[str, tuple[str, list[str]]] = {
        "openai":    ("OPENAI_API_KEY",    []),
        "anthropic": ("ANTHROPIC_API_KEY", []),
        "deepseek":  ("DEEPSEEK_API_KEY",  []),
        "google":    ("GOOGLE_API_KEY",    []),
    }
    for name, cfg in MODEL_REGISTRY.items():
        provider = cfg.provider
        if provider in provider_keys:
            provider_keys[provider][1].append(name)

    result = []
    for provider, (key_name, models) in provider_keys.items():
        api_key = getattr(settings, key_name, "")
        result.append(ApiKeyStatus(
            provider=provider,
            configured=bool(api_key),
            models=models,
        ))
    return result


@router.patch("", response_model=PlannerConfigResponse)
async def update_planner_config(
    body: PlannerConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_config(db)
    if body.system_prompt is not None:
        cfg.system_prompt = body.system_prompt
    if body.model is not None:
        cfg.model = body.model
    if body.max_tasks is not None:
        cfg.max_tasks = body.max_tasks
    if body.max_retries is not None:
        cfg.max_retries = body.max_retries
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.post("/preview", response_model=PlannerPreviewResponse)
async def preview_plan(
    body: PlannerPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run the planner on a test prompt and return tasks without persisting anything."""
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY not configured")

    cfg = await _get_config(db)
    system_prompt = body.system_prompt or cfg.system_prompt

    # Inject custom agents into the prompt
    from app.services.planner import _get_custom_agent_context
    custom_context = await _get_custom_agent_context(db)
    full_prompt = system_prompt + custom_context

    from app.schemas.planner import PlannerOutput

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    for attempt in range(cfg.max_retries):
        try:
            completion = await client.beta.chat.completions.parse(
                model=cfg.model,
                messages=[
                    {"role": "system", "content": full_prompt},
                    {"role": "user", "content": body.prompt},
                ],
                response_format=PlannerOutput,
            )
            parsed = completion.choices[0].message.parsed
            if parsed and parsed.tasks:
                return PlannerPreviewResponse(
                    tasks=[
                        PlannerPreviewTask(
                            prompt=t.prompt,
                            agent_type=t.agent_type,
                            dependencies=t.dependencies,
                            model=t.model,
                        )
                        for t in parsed.tasks
                    ],
                    used_system_prompt=full_prompt,
                )
        except Exception:
            logger.exception(f"Preview plan attempt {attempt + 1} failed")

    raise HTTPException(status_code=500, detail="Planning failed after retries")


@router.post("/modify-prompt", response_model=ModifyPromptResponse)
async def modify_system_prompt(
    body: ModifyPromptRequest,
    db: AsyncSession = Depends(get_db),
):
    """Use an LLM to rewrite the planning system prompt based on an instruction."""
    cfg = await _get_config(db)
    current = body.current_prompt if body.current_prompt is not None else cfg.system_prompt
    model = body.model or get_default_model_for_agent("general")

    system = (
        "You are an expert at writing LLM system prompts for autonomous task planning agents. "
        "You will be given a planning system prompt and an instruction on how to modify it. "
        "Output ONLY the complete modified system prompt — no explanation, no markdown fences."
    )
    user = (
        f"Current system prompt:\n\n{current}\n\n"
        f"Modification instruction: {body.instruction}\n\n"
        "Output only the complete modified prompt."
    )

    try:
        result = await chat_completion(model, [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], max_tokens=4096)
        return ModifyPromptResponse(system_prompt=result.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
