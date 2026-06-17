"""Example: a deliberately looping agent protected by LoopDetectionMiddleware.

This agent intentionally calls the same tool repeatedly to demonstrate
all three recovery strategies in action.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from loop_detector.config import get_settings
from loop_detector.logging import configure_logging, get_logger
from loop_detector.middleware.langgraph import LoopDetectionMiddleware, LoopDetectorConfig

settings = get_settings()
logger = get_logger(__name__)

configure_logging()


# ---- Intentionally broken tools ----

@tool
def search_database(query: str) -> str:
    """Search the database for records matching the query."""
    # Always returns the same result -- simulates a stuck external service
    return "Found 42 records. No further details available."


@tool
def filter_results(criteria: str) -> str:
    """Filter the previously retrieved results by criteria."""
    return "Filtered: still 42 records. Criteria did not narrow results."


@tool
def summarize_and_halt(summary: str) -> str:
    """Call this when you cannot make further progress. Summarise what you found."""
    return f"HALTED. Summary: {summary}"


_TOOLS = [search_database, filter_results, summarize_and_halt]


# ---- Agent state ----

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    tool_name: str
    tool_args: dict
    observation: str
    tokens_used: int
    final_summary: str


# ---- Agent nodes ----

_llm = ChatAnthropic(
    model=settings.llm_model,
    api_key=settings.anthropic_api_key,
).bind_tools(_TOOLS)


async def call_model(state: AgentState) -> AgentState:
    response = await _llm.ainvoke(state["messages"])
    tool_name = ""
    tool_args: dict = {}

    if response.tool_calls:
        tc = response.tool_calls[0]
        tool_name = tc["name"]
        tool_args = tc["args"]

    return {
        **state,
        "messages": [response],
        "tool_name": tool_name,
        "tool_args": tool_args,
        "tokens_used": response.usage_metadata.get("output_tokens", 0) if response.usage_metadata else 0,
    }


async def call_tool(state: AgentState) -> AgentState:
    tool_name = state.get("tool_name", "")
    tool_args = state.get("tool_args", {})

    tool_map = {t.name: t for t in _TOOLS}
    if tool_name not in tool_map:
        observation = "Unknown tool."
    else:
        observation = tool_map[tool_name].invoke(tool_args)

    return {
        **state,
        "messages": [ToolMessage(content=observation, tool_call_id="tc_1")],
        "observation": observation,
    }


def _route(state: AgentState) -> str:
    if state.get("final_summary"):
        return END
    if not state.get("tool_name"):
        return END
    if state["tool_name"] == "summarize_and_halt":
        return END
    return "call_tool"


def build_example_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)
    graph.add_node("call_tool", call_tool)
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", _route)
    graph.add_edge("call_tool", "call_model")
    return graph.compile()


def build_protected_graph() -> LoopDetectionMiddleware:
    base = build_example_graph()
    config = LoopDetectorConfig(
        max_steps=10,
        fingerprint_window=5,
        semantic_threshold=0.90,
        consecutive_detections_for_checkpoint=2,
        goal="Find and summarise user database records",
    )
    return LoopDetectionMiddleware(base, config=config)
