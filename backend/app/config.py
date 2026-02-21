from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./actions.db"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    ANTHROPIC_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    CHROMA_PERSIST_DIR: str = "data/chroma"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    ARXIV_MAX_RESULTS: int = 10
    ARXIV_RAG_TOP_K: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
