"""Shared test fixtures for loop detection tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from loop_detector.models import AgentStep, ToolExecution


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_step(
    tool_name: str = "search",
    args: dict | None = None,
    observation: str = "result",
    step_index: int = 0,
    tokens: int = 100,
) -> AgentStep:
    return AgentStep(
        step_index=step_index,
        tool_execution=ToolExecution(
            tool_name=tool_name,
            args=args or {"query": "test"},
            result=observation,
            started_at=_now(),
            finished_at=_now(),
        ),
        observation=observation,
        tokens_used=tokens,
        timestamp=_now(),
    )


@pytest.fixture
def session_id() -> str:
    return str(uuid.uuid4())
