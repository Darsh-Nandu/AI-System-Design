"""Centralised settings. All thresholds are runtime-configurable, no redeploy needed."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Anthropic
    anthropic_api_key: str = ""

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "refund_agent"
    postgres_user: str = "refund"
    postgres_password: str = "refund_secret"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:19092"
    kafka_audit_topic: str = "refund-audit-log"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Agent thresholds (risk team configures these)
    confidence_threshold: float = 0.85
    escalation_threshold: float = 0.60
    max_auto_refund_amount: Decimal = Decimal("500.00")
    max_refunds_per_24h: int = 5
    refund_window_days: int = 30

    # LLM
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
