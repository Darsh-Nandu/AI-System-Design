"""Runtime configuration via environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Models
    candidate_model: str = "claude-sonnet-4-6"
    judge_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # Database
    database_url: str = "postgresql+asyncpg://eval:eval@localhost:5435/eval_pipeline"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # Eval thresholds
    similarity_filter_threshold: float = 0.95
    code_gen_regression_threshold: float = 0.05
    bug_fix_regression_threshold: float = 0.10
    explanation_regression_threshold: float = 0.30

    # Weighted regression: if weighted score exceeds this, recommend HOLD
    regression_hold_threshold: float = 5.0

    # Code sandbox
    sandbox_timeout_seconds: float = 10.0
    sandbox_memory_mb: int = 256

    # Observability
    metrics_port: int = 9310
    log_level: str = "INFO"

    # API
    api_port: int = 8083


@lru_cache
def get_settings() -> Settings:
    return Settings()
