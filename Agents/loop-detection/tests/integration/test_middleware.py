"""Integration tests for LoopDetectionMiddleware.

These tests use a real (in-memory) LangGraph graph but no external services.
Set SKIP_INTEGRATION=1 to skip when Postgres/Redis are unavailable.
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated, TypedDict

import pytest
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from loop_detector.detector.fingerprint import FingerprintDetector
from loop_detector.middleware.langgraph import LoopDetectionMiddleware, LoopDetectorConfig
from loop_detector.models import AgentStep, ToolExecution

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION", "0") == "1",
    reason="Integration tests require running infrastructure",
)


class SimpleState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    counter: int


async def counting_node(state: SimpleState) -> SimpleState:
    return {**state, "counter": state.get("counter", 0) + 1}


def _stop_at_five(state: SimpleState) -> str:
    return END if state.get("counter", 0) >= 5 else "count"


def build_counting_graph():
    g = StateGraph(SimpleState)
    g.add_node("count", counting_node)
    g.add_edge(START, "count")
    g.add_conditional_edges("count", _stop_at_five)
    return g.compile()


@pytest.mark.asyncio
async def test_middleware_passes_through_normal_graph() -> None:
    base = build_counting_graph()
    config = LoopDetectorConfig(max_steps=20, enable_monitoring=False)
    wrapped = LoopDetectionMiddleware(base, config=config)

    result = await wrapped.ainvoke(
        {"messages": [HumanMessage(content="start")], "counter": 0},
        config={"configurable": {"thread_id": str(uuid.uuid4())}},
    )
    assert result["counter"] == 5


@pytest.mark.asyncio
async def test_fingerprint_detector_isolated() -> None:
    """Fingerprint detector triggers on exact repeated tool calls (no infra needed)."""
    detector = FingerprintDetector(window=5)
    session_id = str(uuid.uuid4())

    from tests.conftest import make_step

    step = make_step(tool_name="search", args={"q": "hello"}, step_index=0)
    assert detector.check(step, session_id) is None

    step2 = make_step(tool_name="search", args={"q": "hello"}, step_index=1)
    signal = detector.check(step2, session_id)
    assert signal is not None
