"""Prometheus metrics for the eval pipeline."""

from prometheus_client import Counter, Gauge, Histogram, start_http_server

eval_runs_total = Counter(
    "eval_runs_total",
    "Total eval runs by status",
    ["status"],
)

entries_evaluated_total = Counter(
    "eval_entries_evaluated_total",
    "Log entries evaluated by task type",
    ["task_type"],
)

entries_filtered_total = Counter(
    "eval_entries_filtered_total",
    "Entries skipped by similarity pre-filter",
)

regressions_detected_total = Counter(
    "eval_regressions_detected_total",
    "Regression flags raised by task type",
    ["task_type"],
)

improvements_detected_total = Counter(
    "eval_improvements_detected_total",
    "Improvement flags raised by task type",
    ["task_type"],
)

pass_rate_gauge = Gauge(
    "eval_pass_rate",
    "Current pass rate by task type and model",
    ["task_type", "model_role"],
)

judge_latency = Histogram(
    "eval_judge_latency_seconds",
    "Time for one LLM judge call",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

sandbox_latency = Histogram(
    "eval_sandbox_latency_seconds",
    "Time to execute code in sandbox",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

ship_decision_gauge = Gauge(
    "eval_ship_decision",
    "Latest ship/hold/review decision (1=ship, 0=review, -1=hold)",
)


def start_metrics_server(port: int = 9310) -> None:
    start_http_server(port)
