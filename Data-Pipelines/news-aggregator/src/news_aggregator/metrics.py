"""Prometheus metrics for the pipeline."""

from prometheus_client import Counter, Gauge, Histogram, start_http_server

articles_ingested_total = Counter(
    "news_articles_ingested_total",
    "Total articles published to Kafka",
    ["source"],
)

articles_processed_total = Counter(
    "news_articles_processed_total",
    "Total articles processed by workers",
    ["status"],  # accepted, duplicate, clustered, error
)

articles_stale_marked_total = Counter(
    "news_articles_stale_marked_total",
    "Total articles marked stale by invalidation",
)

dedup_stage1_hits_total = Counter(
    "news_dedup_stage1_hits_total",
    "Articles eliminated by entity fingerprint pre-filter",
)

dedup_stage2_checks_total = Counter(
    "news_dedup_stage2_checks_total",
    "Articles that reached cosine similarity check",
    ["result"],  # accepted, duplicate, clustered
)

processing_duration_seconds = Histogram(
    "news_article_processing_seconds",
    "End-to-end article processing time",
    ["stage"],  # enrich, embed, dedup, write
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

kafka_consumer_lag = Gauge(
    "news_kafka_consumer_lag",
    "Current consumer group lag",
    ["topic", "partition"],
)

qdrant_collection_size = Gauge(
    "news_qdrant_collection_size",
    "Number of vectors in each Qdrant collection",
    ["collection"],
)


def start_metrics_server(port: int = 9100) -> None:
    start_http_server(port)
