"""Stratified sampling to ensure balanced task-type coverage in each eval run."""

from __future__ import annotations

import random
from collections import defaultdict

from eval_pipeline.models import LogEntry, TaskType


def stratified_sample(
    entries: list[LogEntry],
    per_task_type: int = 100,
    seed: int = 42,
) -> list[LogEntry]:
    """Return up to `per_task_type` entries per TaskType, shuffled deterministically."""
    rng = random.Random(seed)
    buckets: dict[TaskType, list[LogEntry]] = defaultdict(list)
    for entry in entries:
        buckets[entry.task_type].append(entry)

    sampled: list[LogEntry] = []
    for task_type in TaskType:
        bucket = buckets[task_type]
        rng.shuffle(bucket)
        sampled.extend(bucket[:per_task_type])

    rng.shuffle(sampled)
    return sampled


def prioritise_high_signal(entries: list[LogEntry]) -> list[LogEntry]:
    """Sort entries so high-implicit-weight items are evaluated first."""
    return sorted(entries, key=lambda e: e.implicit_signals.quality_weight, reverse=True)
