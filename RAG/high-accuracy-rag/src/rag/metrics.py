"""Prometheus metrics for the RAG system."""

from prometheus_client import Counter, Histogram, Summary, start_http_server

queries_total = Counter("rag_queries_total", "Total queries processed", ["status"])

ingestion_total = Counter("rag_ingestion_total", "Documents ingested", ["status"])

chunks_retrieved = Counter("rag_chunks_retrieved_total", "Chunks fetched before reranking")
chunks_passed_crag = Counter("rag_chunks_passed_crag_total", "Chunks passing CRAG verifier")
chunks_rejected_crag = Counter("rag_chunks_rejected_crag_total", "Chunks rejected by CRAG verifier")

faithfulness_score = Summary(
    "rag_faithfulness_score",
    "Per-query faithfulness score (fraction of grounded claims)",
)

ungrounded_claims_total = Counter(
    "rag_ungrounded_claims_total",
    "Claims removed or flagged due to no source grounding",
)

query_latency = Histogram(
    "rag_query_latency_seconds",
    "End-to-end query latency",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

rerank_latency = Histogram(
    "rag_rerank_latency_seconds",
    "Cross-encoder reranking latency",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0],
)

crag_latency = Histogram(
    "rag_crag_latency_seconds",
    "CRAG verifier LLM call latency",
    buckets=[0.5, 1.0, 2.0, 5.0],
)

freshness_hours = Histogram(
    "rag_index_freshness_hours",
    "Hours since last ingestion by doc_type",
    ["doc_type"],
    buckets=[1, 6, 12, 24, 48, 72],
)


def start_metrics_server(port: int = 9320) -> None:
    start_http_server(port)
