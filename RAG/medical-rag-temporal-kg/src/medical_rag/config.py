"""Runtime-configurable settings via pydantic-settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    anthropic_api_key: str = Field(default="sk-placeholder")
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 4096

    # Database
    database_url: str = "postgresql+asyncpg://medical:medical@localhost:5437/medical_rag"

    # Qdrant
    qdrant_url: str = "http://localhost:6334"
    qdrant_findings_collection: str = "medical_findings"
    qdrant_timelines_collection: str = "patient_timelines"
    qdrant_embedding_dim: int = 384

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "medical_rag_password"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # PII
    date_shift_seed_salt: str = "hipaa-date-shift-salt-v1"
    max_date_shift_days: int = 90

    # Retrieval thresholds
    faithfulness_threshold: float = 0.65
    crag_relevance_threshold: float = 0.70
    high_confidence_threshold: float = 0.90
    medium_confidence_threshold: float = 0.70
    cbr_top_k: int = 5
    retrieval_top_k: int = 10

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8085
    api_workers: int = 1

    # Observability
    prometheus_port: int = 8086
    log_level: str = "INFO"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
