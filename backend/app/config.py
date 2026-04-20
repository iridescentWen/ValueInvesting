from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    llm_model: str = "anthropic:claude-sonnet-4-6"

    tushare_token: str | None = None
    akshare_rate_limit: int = 10

    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    duckdb_path: Path = Path("./data/analytics.duckdb")

    log_level: str = "INFO"
    env: str = "development"
    cors_origins: list[str] = ["http://localhost:8420"]

    def require_llm_key(self) -> None:
        provider = self.llm_model.split(":", 1)[0]
        if provider == "anthropic" and not self.anthropic_api_key:
            raise RuntimeError("LLM_MODEL is Anthropic but ANTHROPIC_API_KEY is unset")
        if provider == "openai" and not self.openai_api_key:
            raise RuntimeError("LLM_MODEL is OpenAI but OPENAI_API_KEY is unset")


settings = Settings()
