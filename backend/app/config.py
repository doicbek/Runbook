from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./actions.db"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5"
    ANTHROPIC_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    CHROMA_PERSIST_DIR: str = "data/chroma"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    ARXIV_MAX_RESULTS: int = 10
    ARXIV_RAG_TOP_K: int = 5
    ITERATION_RETENTION_DAYS: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# Per-agent-type timeout defaults (seconds)
AGENT_TIMEOUTS: dict[str, int] = {
    "code_execution": 600,
    "coding": 900,
    "sub_action": 1200,
    "default": 300,
}

# LLM pricing per 1M tokens: {model_id: {input: USD, output: USD}}
LLM_PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "openai/gpt-5": {"input": 10.0, "output": 30.0},
    "openai/gpt-5-mini": {"input": 1.50, "output": 6.0},
    "openai/gpt-5-nano": {"input": 0.50, "output": 2.0},
    "openai/gpt-4.1": {"input": 2.0, "output": 8.0},
    "openai/gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "openai/gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "openai/o3": {"input": 10.0, "output": 40.0},
    "openai/o3-mini": {"input": 1.10, "output": 4.40},
    "openai/o4-mini": {"input": 1.10, "output": 4.40},
    "openai/gpt-4o": {"input": 2.50, "output": 10.0},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    # Anthropic
    "anthropic/claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "anthropic/claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "anthropic/claude-haiku-4-5": {"input": 0.80, "output": 4.0},
    "anthropic/claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    # Google
    "google/gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "google/gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "google/gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "google/gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    # DeepSeek
    "deepseek/deepseek-chat": {"input": 0.27, "output": 1.10},
}
