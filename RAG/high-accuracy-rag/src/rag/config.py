"""Runtime configuration via environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    llm_model: str = "claude-sonnet-4-6"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    card_collection: str = "legal_document_cards"
    chunk_collection: str = "legal_chunks"
    embedding_dim: int = 384

    # Database
    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5436/high_accuracy_rag"

    # Retrieval thresholds
    card_top_k: int = 20
    chunk_top_k: int = 50
    rerank_top_k: int = 10
    similarity_filter_threshold: float = 0.95
    faithfulness_threshold: float = 0.70
    crag_score_threshold: float = 0.0

    # Chunking
    chunk_size: int = 1500
    chunk_overlap: int = 150

    # Freshness
    freshness_alert_hours: int = 24

    # API
    api_port: int = 8084
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
