"""Prometheus metrics for the refund agent."""

from prometheus_client import Counter, Histogram, start_http_server

velocity_checks_total = Counter(
    "refund_velocity_checks_total",
    "Velocity check outcomes",
    ["result"],  # ok, blocked
)

eligibility_checks_total = Counter(
    "refund_eligibility_checks_total",
    "Eligibility check outcomes per transaction",
    ["result"],  # eligible, ineligible, already_refunded
)

evidence_grades_total = Counter(
    "refund_evidence_grades_total",
    "Evidence confidence levels assigned by Claude",
    ["level"],  # high, medium, low
)

magnitude_checks_total = Counter(
    "refund_magnitude_checks_total",
    "Magnitude gate outcomes",
    ["result"],  # ok, escalated
)

refunds_executed_total = Counter(
    "refund_executions_total",
    "Individual refund execution outcomes",
    ["status"],  # success, failed
)

escalations_total = Counter(
    "refund_escalations_total",
    "Sessions escalated to human agents",
    ["reason"],  # low_confidence, high_amount, velocity_exceeded, system_error
)

agent_pipeline_duration = Histogram(
    "refund_agent_pipeline_seconds",
    "End-to-end agent pipeline duration",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)


def start_metrics_server(port: int = 9200) -> None:
    start_http_server(port)
