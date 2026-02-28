"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the AI Enterprise Tool."""

    model_config = {"env_prefix": "AET_", "env_file": ".env", "extra": "ignore"}

    # --- Application ---
    app_name: str = "AI Enterprise Tool"
    company_name: str = "Acme Corp"
    debug: bool = False

    # --- Anthropic ---
    anthropic_api_key: str = ""
    opus_model: str = "claude-sonnet-4-20250514"
    sonnet_model: str = "claude-sonnet-4-20250514"
    max_context_tokens: int = 150_000

    # --- GitHub ---
    github_token: str = ""
    github_webhook_secret: str = ""

    # --- Slack ---
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_indexed_channels: list[str] = Field(default_factory=list)

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "enterprise_knowledge"

    # --- PostgreSQL ---
    database_url: str = "postgresql+asyncpg://localhost:5432/aet"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Embedding ---
    embedding_model: str = "text-embedding-3-large"
    embedding_dimension: int = 3072
    openai_api_key: str = ""

    # --- Staleness ---
    staleness_threshold_days: int = 540  # 18 months


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached singleton settings instance."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()
    return _settings
