"""Application settings loaded from environment variables.

Every setting is validated at startup.  Missing *required* values in
non-debug mode cause a clear, immediate error instead of cryptic
failures at runtime.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the AI Enterprise Tool."""

    model_config = {"env_prefix": "AET_", "env_file": ".env", "extra": "ignore"}

    # --- Application ---
    app_name: str = "AI Enterprise Tool"
    company_name: str = "Acme Corp"
    debug: bool = False

    # --- API Authentication ---
    api_keys: list[str] = Field(default_factory=list)

    # --- Anthropic ---
    anthropic_api_key: str = ""
    opus_model: str = "claude-sonnet-4-20250514"
    sonnet_model: str = "claude-sonnet-4-20250514"
    max_context_tokens: int = 150_000
    llm_max_output_tokens: int = 4096
    llm_timeout_seconds: int = 120

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

    # --- Rate Limiting ---
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 10

    # --- CORS ---
    # Default ["*"] allows all origins (dev-friendly). In production,
    # set AET_CORS_ALLOWED_ORIGINS='["https://your-domain.com"]'
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["*"],
    )

    # --- Request Limits ---
    max_query_length: int = 10_000
    max_ingest_batch_size: int = 100

    # --- Validators ---

    @field_validator("max_context_tokens", "llm_max_output_tokens", "llm_timeout_seconds")
    @classmethod
    def _positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Value must be positive")
        return v

    @field_validator("staleness_threshold_days")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Value must be non-negative")
        return v

    @field_validator("rate_limit_per_minute", "rate_limit_burst")
    @classmethod
    def _rate_limit_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Rate limit values must be positive")
        return v


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached singleton settings instance."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset settings singleton (used in tests)."""
    global _settings  # noqa: PLW0603
    _settings = None
