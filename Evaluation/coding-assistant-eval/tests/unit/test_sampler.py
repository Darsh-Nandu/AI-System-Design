"""Unit tests for stratified sampling."""

from __future__ import annotations

from eval_pipeline.dataset.sampler import prioritise_high_signal, stratified_sample
from eval_pipeline.models import ImplicitSignals, LogEntry, TaskType


def _make_entries(n_per_type: int) -> list[LogEntry]:
    entries = []
    for task_type in TaskType:
        for i in range(n_per_type):
            entries.append(
                LogEntry(
                    prompt=f"prompt {task_type} {i}",
                    old_model_output=f"output {i}",
                    task_type=task_type,
                    implicit_signals=ImplicitSignals(
                        copied=i % 2 == 0,
                        edit_distance_after_copy=0.1 * (i % 10),
                    ),
                )
            )
    return entries


def test_stratified_sample_respects_per_task_limit() -> None:
    entries = _make_entries(200)
    sampled = stratified_sample(entries, per_task_type=50)
    by_type: dict[TaskType, int] = {}
    for e in sampled:
        by_type[e.task_type] = by_type.get(e.task_type, 0) + 1
    for count in by_type.values():
        assert count <= 50


def test_stratified_sample_is_deterministic() -> None:
    entries = _make_entries(100)
    a = [e.id for e in stratified_sample(entries, seed=42)]
    b = [e.id for e in stratified_sample(entries, seed=42)]
    assert a == b


def test_prioritise_puts_high_signal_first() -> None:
    entries = _make_entries(10)
    ordered = prioritise_high_signal(entries)
    weights = [e.implicit_signals.quality_weight for e in ordered]
    assert weights == sorted(weights, reverse=True)
