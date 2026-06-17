"""Prometheus metrics for the loop detection system."""

from prometheus_client import Counter, Histogram, start_http_server

loop_detections_total = Counter(
    "loop_detections_total",
    "Loop signals detected by type",
    ["signal_type"],
)

recovery_actions_total = Counter(
    "loop_recovery_actions_total",
    "Recovery strategies triggered",
    ["strategy"],
)

fingerprint_hits_total = Counter(
    "loop_fingerprint_hits_total",
    "Exact duplicate fingerprint matches",
)

semantic_hits_total = Counter(
    "loop_semantic_hits_total",
    "Semantic similarity loop detections",
)

budget_exhausted_total = Counter(
    "loop_budget_exhausted_total",
    "Budget exhaustion events",
    ["reason"],  # steps, tokens
)

no_progress_total = Counter(
    "loop_no_progress_total",
    "No-progress detections",
)

causal_cycle_total = Counter(
    "loop_causal_cycles_total",
    "Causal dependency cycle detections",
)

monitor_timeouts_total = Counter(
    "loop_monitor_timeouts_total",
    "Tool execution timeouts detected by monitoring agent",
)

human_checkpoints_total = Counter(
    "loop_human_checkpoints_total",
    "Sessions escalated to human review queue",
)

detection_latency = Histogram(
    "loop_detection_latency_seconds",
    "Time to run all detection layers per step",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)


def start_metrics_server(port: int = 9300) -> None:
    start_http_server(port)
