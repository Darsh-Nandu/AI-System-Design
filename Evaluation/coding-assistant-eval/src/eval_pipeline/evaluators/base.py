"""Abstract base class for all task-specific evaluators."""

from __future__ import annotations

from abc import ABC, abstractmethod

from eval_pipeline.models import LogEntry, TaskResult


class BaseEvaluator(ABC):
    @abstractmethod
    async def evaluate(self, entry: LogEntry, new_output: str) -> TaskResult:
        """Compare old vs new output for a single log entry."""
        ...
