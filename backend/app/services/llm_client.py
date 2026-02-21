import logging
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    provider: str
    model_id: str
    display_name: str
    api_key_setting: str
    base_url: str | None = None


MODEL_REGISTRY: dict[str, ModelConfig] = {
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
    "anthropic/claude-sonnet-4-5-20250929": ModelConfig(
        provider="anthropic",
        model_id="claude-sonnet-4-5-20250929",
        display_name="Claude Sonnet 4.5",
        api_key_setting="ANTHROPIC_API_KEY",
    ),
    "deepseek/deepseek-chat": ModelConfig(
        provider="deepseek",
        model_id="deepseek-chat",
        display_name="DeepSeek Chat",
        api_key_setting="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
    ),
    "google/gemini-2.0-flash": ModelConfig(
        provider="google",
        model_id="gemini-2.0-flash",
        display_name="Gemini 2.0 Flash",
        api_key_setting="GOOGLE_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
}

DEFAULT_MODELS_BY_AGENT_TYPE: dict[str, str] = {
    "arxiv_search": "anthropic/claude-sonnet-4-5-20250929",
    "code_execution": "openai/gpt-4o",
    "report": "anthropic/claude-sonnet-4-5-20250929",
    "data_retrieval": "openai/gpt-4o-mini",
    "spreadsheet": "openai/gpt-4o-mini",
    "general": "openai/gpt-4o",
}

FALLBACK_MODEL = "openai/gpt-4o"


def _get_api_key(setting_name: str) -> str:
    return getattr(settings, setting_name, "")


def get_default_model_for_agent(agent_type: str) -> str:
    """Return the recommended model for an agent type, falling back if the API key is missing."""
    model_name = DEFAULT_MODELS_BY_AGENT_TYPE.get(agent_type, FALLBACK_MODEL)
    config = MODEL_REGISTRY.get(model_name)
    if config and _get_api_key(config.api_key_setting):
        return model_name
    # Fallback to openai/gpt-4o if preferred model's key is missing
    fallback_config = MODEL_REGISTRY.get(FALLBACK_MODEL)
    if fallback_config and _get_api_key(fallback_config.api_key_setting):
        return FALLBACK_MODEL
    # Last resort: return whatever has a key
    for name, cfg in MODEL_REGISTRY.items():
        if _get_api_key(cfg.api_key_setting):
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

    Returns:
        Plain text content from the model response.
    """
    config = MODEL_REGISTRY.get(model)
    if not config:
        raise ValueError(f"Unknown model: {model}. Available: {list(MODEL_REGISTRY.keys())}")

    api_key = _get_api_key(config.api_key_setting)
    if not api_key:
        raise ValueError(f"No API key configured for {model} (set {config.api_key_setting})")

    logger.info(f"Using model: {model}")

    if config.provider == "anthropic":
        return await _anthropic_completion(config, api_key, messages, **kwargs)
    else:
        return await _openai_compatible_completion(config, api_key, messages, **kwargs)


async def _openai_compatible_completion(
    config: ModelConfig, api_key: str, messages: list[dict], **kwargs
) -> str:
    """Handle OpenAI, DeepSeek, and Google Gemini (all OpenAI-compatible)."""
    from openai import AsyncOpenAI

    client_kwargs: dict = {"api_key": api_key}
    if config.base_url:
        client_kwargs["base_url"] = config.base_url

    client = AsyncOpenAI(**client_kwargs)
    response = await client.chat.completions.create(
        model=config.model_id,
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content or ""


async def _anthropic_completion(
    config: ModelConfig, api_key: str, messages: list[dict], **kwargs
) -> str:
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
    return response.content[0].text if response.content else ""
