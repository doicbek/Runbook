import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from app.config import LLM_PRICING, settings

logger = logging.getLogger(__name__)


async def _record_llm_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    action_id: str | None = None,
    task_id: str | None = None,
) -> None:
    """Record LLM usage in the database and optionally publish SSE cost event."""
    pricing = LLM_PRICING.get(model, {"input": 0.0, "output": 0.0})
    cost_usd = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

    try:
        from app.database import async_session
        from app.models.llm_usage import LLMUsage

        async with async_session() as session:
            usage = LLMUsage(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                action_id=action_id,
                task_id=task_id,
            )
            session.add(usage)
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to record LLM usage: {e}")

    if action_id:
        try:
            from sqlalchemy import func, select

            from app.database import async_session
            from app.models.llm_usage import LLMUsage
            from app.services.event_bus import event_bus

            async with async_session() as session:
                result = await session.execute(
                    select(func.sum(LLMUsage.cost_usd)).where(LLMUsage.action_id == action_id)
                )
                total_cost = result.scalar() or 0.0

            await event_bus.publish(action_id, "cost.update", {
                "action_id": action_id,
                "total_cost_usd": round(total_cost, 6),
                "task_id": task_id,
                "model": model,
                "cost_usd": round(cost_usd, 6),
            })
        except Exception as e:
            logger.warning(f"Failed to publish cost update: {e}")


@dataclass
class ModelConfig:
    provider: str
    model_id: str
    display_name: str
    api_key_setting: str
    base_url: str | None = None


MODEL_REGISTRY: dict[str, ModelConfig] = {
    # ── OpenAI ────────────────────────────────────────────────────────────────
    "openai/gpt-5": ModelConfig(
        provider="openai",
        model_id="gpt-5",
        display_name="GPT-5",
        api_key_setting="OPENAI_API_KEY",
    ),
    "openai/gpt-5-mini": ModelConfig(
        provider="openai",
        model_id="gpt-5-mini",
        display_name="GPT-5 Mini",
        api_key_setting="OPENAI_API_KEY",
    ),
    "openai/gpt-5-nano": ModelConfig(
        provider="openai",
        model_id="gpt-5-nano",
        display_name="GPT-5 Nano",
        api_key_setting="OPENAI_API_KEY",
    ),
    "openai/gpt-4.1": ModelConfig(
        provider="openai",
        model_id="gpt-4.1",
        display_name="GPT-4.1",
        api_key_setting="OPENAI_API_KEY",
    ),
    "openai/gpt-4.1-mini": ModelConfig(
        provider="openai",
        model_id="gpt-4.1-mini",
        display_name="GPT-4.1 Mini",
        api_key_setting="OPENAI_API_KEY",
    ),
    "openai/gpt-4.1-nano": ModelConfig(
        provider="openai",
        model_id="gpt-4.1-nano",
        display_name="GPT-4.1 Nano",
        api_key_setting="OPENAI_API_KEY",
    ),
    "openai/o3": ModelConfig(
        provider="openai",
        model_id="o3",
        display_name="o3",
        api_key_setting="OPENAI_API_KEY",
    ),
    "openai/o3-mini": ModelConfig(
        provider="openai",
        model_id="o3-mini",
        display_name="o3-mini",
        api_key_setting="OPENAI_API_KEY",
    ),
    "openai/o4-mini": ModelConfig(
        provider="openai",
        model_id="o4-mini",
        display_name="o4-mini",
        api_key_setting="OPENAI_API_KEY",
    ),
    "openai/gpt-4o": ModelConfig(
        provider="openai",
        model_id="gpt-4o",
        display_name="GPT-4o",
        api_key_setting="OPENAI_API_KEY",
    ),
    "openai/gpt-4o-mini": ModelConfig(
        provider="openai",
        model_id="gpt-4o-mini",
        display_name="GPT-4o Mini",
        api_key_setting="OPENAI_API_KEY",
    ),
    # ── Anthropic ─────────────────────────────────────────────────────────────
    "anthropic/claude-opus-4-6": ModelConfig(
        provider="anthropic",
        model_id="claude-opus-4-6",
        display_name="Claude Opus 4.6",
        api_key_setting="ANTHROPIC_API_KEY",
    ),
    "anthropic/claude-sonnet-4-6": ModelConfig(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        api_key_setting="ANTHROPIC_API_KEY",
    ),
    "anthropic/claude-haiku-4-5": ModelConfig(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
        display_name="Claude Haiku 4.5",
        api_key_setting="ANTHROPIC_API_KEY",
    ),
    "anthropic/claude-sonnet-4-5-20250929": ModelConfig(
        provider="anthropic",
        model_id="claude-sonnet-4-5-20250929",
        display_name="Claude Sonnet 4.5",
        api_key_setting="ANTHROPIC_API_KEY",
    ),
    # ── Google ────────────────────────────────────────────────────────────────
    "google/gemini-2.5-pro": ModelConfig(
        provider="google",
        model_id="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        api_key_setting="GOOGLE_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    "google/gemini-2.5-flash": ModelConfig(
        provider="google",
        model_id="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        api_key_setting="GOOGLE_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    "google/gemini-2.5-flash-lite": ModelConfig(
        provider="google",
        model_id="gemini-2.5-flash-lite",
        display_name="Gemini 2.5 Flash Lite",
        api_key_setting="GOOGLE_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    "google/gemini-2.0-flash": ModelConfig(
        provider="google",
        model_id="gemini-2.0-flash",
        display_name="Gemini 2.0 Flash",
        api_key_setting="GOOGLE_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    # ── DeepSeek ──────────────────────────────────────────────────────────────
    "deepseek/deepseek-chat": ModelConfig(
        provider="deepseek",
        model_id="deepseek-chat",
        display_name="DeepSeek Chat",
        api_key_setting="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
    ),
}

DEFAULT_MODELS_BY_AGENT_TYPE: dict[str, str] = {
    "arxiv_search": "anthropic/claude-sonnet-4-6",
    "code_execution": "anthropic/claude-sonnet-4-6",
    "report": "anthropic/claude-sonnet-4-6",
    "data_retrieval": "google/gemini-2.5-flash",
    "spreadsheet": "anthropic/claude-sonnet-4-6",
    "coding": "anthropic/claude-opus-4-6",
    "general": "anthropic/claude-sonnet-4-6",
    "mcp": "anthropic/claude-sonnet-4-6",
}

FALLBACK_MODEL = "anthropic/claude-sonnet-4-6"

# Cheap utility models ordered by preference — used by utility_completion()
UTILITY_MODEL_CHAIN: list[str] = [
    "google/gemini-2.5-flash",
    "deepseek/deepseek-chat",
    "openai/gpt-5-mini",
]

# Planner models ordered by preference — used by planner_completion()
PLANNER_MODEL_CHAIN: list[str] = [
    "anthropic/claude-opus-4-6",
    "anthropic/claude-sonnet-4-6",
    "google/gemini-2.5-pro",
    "openai/gpt-5",
]


def _get_api_key(setting_name: str) -> str:
    return getattr(settings, setting_name, "")


def get_default_model_for_agent(agent_type: str) -> str:
    """Return the recommended model for an agent type, falling back if the API key is missing.

    Fallback priority: Anthropic models -> Google models -> OpenAI models.
    """
    model_name = DEFAULT_MODELS_BY_AGENT_TYPE.get(agent_type, FALLBACK_MODEL)
    config = MODEL_REGISTRY.get(model_name)
    if config and _get_api_key(config.api_key_setting):
        return model_name
    # Fallback if preferred model's key is missing
    fallback_config = MODEL_REGISTRY.get(FALLBACK_MODEL)
    if fallback_config and _get_api_key(fallback_config.api_key_setting):
        return FALLBACK_MODEL
    # Try providers in priority order: Anthropic -> Google -> OpenAI/others
    _PROVIDER_PRIORITY = ["anthropic", "google", "openai", "deepseek"]
    for provider in _PROVIDER_PRIORITY:
        for name, cfg in MODEL_REGISTRY.items():
            if cfg.provider == provider and _get_api_key(cfg.api_key_setting):
                return name
    return FALLBACK_MODEL


def get_available_models() -> list[dict]:
    """Return models that have configured API keys."""
    result = []
    for name, config in MODEL_REGISTRY.items():
        if _get_api_key(config.api_key_setting):
            result.append({
                "name": name,
                "display_name": config.display_name,
                "provider": config.provider,
            })
    return result


async def chat_completion(model: str, messages: list[dict], **kwargs) -> str:
    """Unified chat completion interface across all providers.

    Args:
        model: Model name in "provider/model_id" format (e.g. "openai/gpt-4o")
        messages: List of message dicts with "role" and "content" keys
        **kwargs: Additional kwargs passed to the provider (max_tokens, temperature, etc.)
            Special kwargs (not passed to provider):
            - action_id: Optional action ID for cost tracking
            - task_id: Optional task ID for cost tracking

    Returns:
        Plain text content from the model response.
    """
    action_id = kwargs.pop("action_id", None)
    task_id = kwargs.pop("task_id", None)

    config = MODEL_REGISTRY.get(model)
    if not config:
        raise ValueError(f"Unknown model: {model}. Available: {list(MODEL_REGISTRY.keys())}")

    api_key = _get_api_key(config.api_key_setting)
    if not api_key:
        raise ValueError(f"No API key configured for {model} (set {config.api_key_setting})")

    logger.info(f"Using model: {model}")

    if config.provider == "anthropic":
        text, usage = await _anthropic_completion(config, api_key, messages, **kwargs)
    else:
        text, usage = await _openai_compatible_completion(config, api_key, messages, **kwargs)

    if usage["input_tokens"] > 0 or usage["output_tokens"] > 0:
        asyncio.create_task(_record_llm_usage(
            model=model,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            action_id=action_id,
            task_id=task_id,
        ))

    return text


async def chat_completion_stream(
    model: str, messages: list[dict], **kwargs
) -> AsyncGenerator[str, None]:
    """Streaming chat completion interface across all providers.

    Yields text chunks as they arrive from the model.

    Args:
        model: Model name in "provider/model_id" format
        messages: List of message dicts with "role" and "content" keys
        **kwargs: Additional kwargs passed to the provider
            Special kwargs (not passed to provider):
            - action_id: Optional action ID for cost tracking
            - task_id: Optional task ID for cost tracking

    Yields:
        Text chunks from the model response.
    """
    action_id = kwargs.pop("action_id", None)
    task_id = kwargs.pop("task_id", None)

    config = MODEL_REGISTRY.get(model)
    if not config:
        raise ValueError(f"Unknown model: {model}. Available: {list(MODEL_REGISTRY.keys())}")

    api_key = _get_api_key(config.api_key_setting)
    if not api_key:
        raise ValueError(f"No API key configured for {model} (set {config.api_key_setting})")

    logger.info(f"Streaming model: {model}")

    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

    if config.provider == "anthropic":
        async for chunk in _anthropic_stream(config, api_key, messages, usage, **kwargs):
            yield chunk
    else:
        async for chunk in _openai_compatible_stream(config, api_key, messages, usage, **kwargs):
            yield chunk

    if usage["input_tokens"] > 0 or usage["output_tokens"] > 0:
        asyncio.create_task(_record_llm_usage(
            model=model,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            action_id=action_id,
            task_id=task_id,
        ))


async def chat_completion_with_tool(
    model: str,
    messages: list[dict],
    tool_name: str,
    tool_schema: dict,
    **kwargs,
) -> dict | None:
    """Call an LLM with a single tool definition and return the parsed tool call arguments.

    For Anthropic: uses tool_use with tool_choice={"type": "tool", "name": tool_name}.
    For OpenAI-compatible: uses tools with tool_choice={"type": "function", "function": {"name": tool_name}}.

    Args:
        model: Model name in "provider/model_id" format
        messages: List of message dicts
        tool_name: Name of the tool
        tool_schema: JSON schema for the tool's input parameters
        **kwargs: Additional provider kwargs (max_tokens, temperature, etc.)

    Returns:
        Parsed dict of tool call arguments, or None if the model didn't call the tool.
    """
    import json as _json

    config = MODEL_REGISTRY.get(model)
    if not config:
        raise ValueError(f"Unknown model: {model}. Available: {list(MODEL_REGISTRY.keys())}")

    api_key = _get_api_key(config.api_key_setting)
    if not api_key:
        raise ValueError(f"No API key configured for {model} (set {config.api_key_setting})")

    logger.info(f"Using model (tool call): {model}")

    if config.provider == "anthropic":
        return await _anthropic_tool_call(config, api_key, messages, tool_name, tool_schema, **kwargs)
    else:
        return await _openai_tool_call(config, api_key, messages, tool_name, tool_schema, **kwargs)


async def _anthropic_tool_call(
    config: ModelConfig,
    api_key: str,
    messages: list[dict],
    tool_name: str,
    tool_schema: dict,
    **kwargs,
) -> dict | None:
    """Anthropic tool_use: define a tool and force the model to call it."""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)

    system_text = ""
    filtered_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_text += msg["content"] + "\n"
        else:
            filtered_messages.append({"role": msg["role"], "content": msg["content"]})

    max_tokens = kwargs.pop("max_tokens", 8192)

    anthropic_kwargs: dict = {
        "model": config.model_id,
        "messages": filtered_messages,
        "max_tokens": max_tokens,
        "tools": [
            {
                "name": tool_name,
                "description": f"Output structured data matching the {tool_name} schema.",
                "input_schema": tool_schema,
            }
        ],
        "tool_choice": {"type": "tool", "name": tool_name},
    }
    if system_text.strip():
        anthropic_kwargs["system"] = system_text.strip()
    if "temperature" in kwargs:
        anthropic_kwargs["temperature"] = kwargs.pop("temperature")

    response = await client.messages.create(**anthropic_kwargs)

    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input  # type: ignore[return-value]
    return None


async def _openai_tool_call(
    config: ModelConfig,
    api_key: str,
    messages: list[dict],
    tool_name: str,
    tool_schema: dict,
    **kwargs,
) -> dict | None:
    """OpenAI-compatible tool call: define a function tool and force the model to call it."""
    import json as _json
    from openai import AsyncOpenAI

    client_kwargs: dict = {"api_key": api_key}
    if config.base_url:
        client_kwargs["base_url"] = config.base_url

    if config.provider == "openai" and config.model_id in _MAX_COMPLETION_TOKENS_MODELS:
        if "max_tokens" in kwargs:
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
        kwargs.pop("temperature", None)

    client = AsyncOpenAI(**client_kwargs)
    response = await client.chat.completions.create(
        model=config.model_id,
        messages=messages,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": f"Output structured data matching the {tool_name} schema.",
                    "parameters": tool_schema,
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": tool_name}},
        **kwargs,
    )
    msg = response.choices[0].message
    if msg.tool_calls:
        return _json.loads(msg.tool_calls[0].function.arguments)
    return None


async def utility_completion(messages: list[dict], **kwargs) -> str:
    """Cheap utility LLM call with automatic fallback chain.

    Iterates UTILITY_MODEL_CHAIN, skipping models without API keys.
    If a model errors at runtime, catches the exception and tries the next.
    Raises the last exception if all models fail.
    """
    last_exc: Exception | None = None
    for model in UTILITY_MODEL_CHAIN:
        config = MODEL_REGISTRY.get(model)
        if not config:
            continue
        api_key = _get_api_key(config.api_key_setting)
        if not api_key:
            logger.debug(f"utility_completion: skipping {model} (no API key)")
            continue
        try:
            return await chat_completion(model, messages, **kwargs)
        except Exception as exc:
            logger.warning(f"utility_completion: {model} failed: {exc}")
            last_exc = exc
    if last_exc is not None:
        raise last_exc
    raise ValueError(
        "utility_completion: no models available. "
        "Set at least one API key for: "
        + ", ".join(UTILITY_MODEL_CHAIN)
    )


async def planner_completion(
    messages: list[dict],
    tool_name: str,
    tool_schema: dict,
    model_override: str | None = None,
    **kwargs,
) -> dict | None:
    """Planner LLM call with fallback chain, using tool_use for structured output.

    If model_override is set, tries that model first. Then iterates PLANNER_MODEL_CHAIN.
    """
    chain = list(PLANNER_MODEL_CHAIN)
    if model_override:
        # Put override at front, remove from chain to avoid double-trying
        chain = [model_override] + [m for m in chain if m != model_override]

    last_exc: Exception | None = None
    for model in chain:
        config = MODEL_REGISTRY.get(model)
        if not config:
            continue
        api_key = _get_api_key(config.api_key_setting)
        if not api_key:
            logger.debug(f"planner_completion: skipping {model} (no API key)")
            continue
        try:
            result = await chat_completion_with_tool(model, messages, tool_name, tool_schema, **kwargs)
            return result
        except Exception as exc:
            logger.warning(f"planner_completion: {model} failed: {exc}")
            last_exc = exc
    if last_exc is not None:
        raise last_exc
    raise ValueError(
        "planner_completion: no models available. "
        "Set at least one API key for: "
        + ", ".join(PLANNER_MODEL_CHAIN)
    )


# Models that require max_completion_tokens instead of max_tokens
_MAX_COMPLETION_TOKENS_MODELS = {
    "gpt-5", "gpt-5-mini", "gpt-5-nano",
    "o1", "o1-mini", "o1-preview",
    "o3", "o3-mini", "o4-mini",
}


async def _openai_compatible_completion(
    config: ModelConfig, api_key: str, messages: list[dict], **kwargs
) -> tuple[str, dict[str, int]]:
    """Handle OpenAI, DeepSeek, and Google Gemini (all OpenAI-compatible)."""
    from openai import AsyncOpenAI

    client_kwargs: dict = {"api_key": api_key}
    if config.base_url:
        client_kwargs["base_url"] = config.base_url

    # Newer OpenAI models (gpt-5, o-series) use max_completion_tokens
    if config.provider == "openai" and config.model_id in _MAX_COMPLETION_TOKENS_MODELS:
        if "max_tokens" in kwargs:
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
        # These models also don't support temperature
        kwargs.pop("temperature", None)

    client = AsyncOpenAI(**client_kwargs)
    response = await client.chat.completions.create(
        model=config.model_id,
        messages=messages,
        **kwargs,
    )
    text = response.choices[0].message.content or ""
    usage = {"input_tokens": 0, "output_tokens": 0}
    if response.usage:
        usage["input_tokens"] = response.usage.prompt_tokens or 0
        usage["output_tokens"] = response.usage.completion_tokens or 0
    return text, usage


async def _anthropic_completion(
    config: ModelConfig, api_key: str, messages: list[dict], **kwargs
) -> tuple[str, dict[str, int]]:
    """Handle Anthropic models (different API format)."""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)

    # Extract system message (Anthropic uses a separate `system` param)
    system_text = ""
    filtered_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_text += msg["content"] + "\n"
        else:
            filtered_messages.append({"role": msg["role"], "content": msg["content"]})

    # Anthropic requires max_tokens
    max_tokens = kwargs.pop("max_tokens", 4096)

    anthropic_kwargs: dict = {
        "model": config.model_id,
        "messages": filtered_messages,
        "max_tokens": max_tokens,
    }
    if system_text.strip():
        anthropic_kwargs["system"] = system_text.strip()

    # Pass through temperature if provided
    if "temperature" in kwargs:
        anthropic_kwargs["temperature"] = kwargs.pop("temperature")

    response = await client.messages.create(**anthropic_kwargs)
    text = response.content[0].text if response.content else ""
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return text, usage


async def _anthropic_stream(
    config: ModelConfig, api_key: str, messages: list[dict], usage_out: dict[str, int], **kwargs
) -> AsyncGenerator[str, None]:
    """Stream text deltas from Anthropic models."""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)

    system_text = ""
    filtered_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_text += msg["content"] + "\n"
        else:
            filtered_messages.append({"role": msg["role"], "content": msg["content"]})

    max_tokens = kwargs.pop("max_tokens", 4096)

    anthropic_kwargs: dict = {
        "model": config.model_id,
        "messages": filtered_messages,
        "max_tokens": max_tokens,
    }
    if system_text.strip():
        anthropic_kwargs["system"] = system_text.strip()
    if "temperature" in kwargs:
        anthropic_kwargs["temperature"] = kwargs.pop("temperature")

    async with client.messages.stream(**anthropic_kwargs) as stream:
        async for text in stream.text_stream:
            yield text
        final = await stream.get_final_message()
        usage_out["input_tokens"] = final.usage.input_tokens
        usage_out["output_tokens"] = final.usage.output_tokens


async def _openai_compatible_stream(
    config: ModelConfig, api_key: str, messages: list[dict], usage_out: dict[str, int], **kwargs
) -> AsyncGenerator[str, None]:
    """Stream text deltas from OpenAI-compatible providers."""
    from openai import AsyncOpenAI

    client_kwargs: dict = {"api_key": api_key}
    if config.base_url:
        client_kwargs["base_url"] = config.base_url

    if config.provider == "openai" and config.model_id in _MAX_COMPLETION_TOKENS_MODELS:
        if "max_tokens" in kwargs:
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
        kwargs.pop("temperature", None)

    client = AsyncOpenAI(**client_kwargs)
    stream = await client.chat.completions.create(
        model=config.model_id,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
        **kwargs,
    )
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
        if chunk.usage:
            usage_out["input_tokens"] = chunk.usage.prompt_tokens or 0
            usage_out["output_tokens"] = chunk.usage.completion_tokens or 0
