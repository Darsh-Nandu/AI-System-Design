"""Centralised settings — all config from environment / .env file."""

from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_raw_articles: str = "raw-articles"
    kafka_consumer_group: str = "news-workers"
    kafka_num_partitions: int = 12
    kafka_replication_factor: int = 1

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "news_aggregator"
    postgres_user: str = "news"
    postgres_password: str = "news_secret"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def postgres_dsn_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_hot: str = "articles_hot"
    qdrant_collection_warm: str = "articles_warm"
    qdrant_collection_cold: str = "articles_cold"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_fingerprint_ttl_seconds: int = 604800

    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Deduplication
    dedup_exact_threshold: float = 0.97
    dedup_cluster_threshold: float = 0.85

    # Workers
    worker_concurrency: int = 10
    worker_batch_size: int = 50

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4

    # Scraper
    scraper_poll_interval_seconds: int = 30
    scraper_request_timeout_seconds: int = 10

    # Checker
    hot_checker_interval_seconds: int = 300
    cold_archive_after_days: int = 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
