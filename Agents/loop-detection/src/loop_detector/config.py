"""Centralised settings -- all detection thresholds are runtime-configurable."""

from __future__ import annotations

from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "loop_detector"
    postgres_user: str = "loop"
    postgres_password: str = "loop_secret"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Detection thresholds
    fingerprint_window: int = 10
    semantic_threshold: float = 0.92
    semantic_window: int = 5
    max_steps: int = 50
    max_tokens: int = 100_000
    progress_window: int = 5
    progress_novelty_threshold: float = 0.05
    consecutive_detections_for_checkpoint: int = 3

    # Monitoring
    monitor_poll_interval_seconds: int = 5
    tool_timeout_multiplier: float = 3.0

    # LLM
    llm_model: str = "claude-sonnet-4-6"


@lru_cache
def get_settings() -> Settings:
    return Settings()
