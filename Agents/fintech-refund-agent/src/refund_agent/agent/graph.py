"""LangGraph state machine for the refund agent.

Node flow:
  ambiguity -> velocity -> eligibility -> evidence -> magnitude -> execution
                |               |             |           |
                v               v             v           v
            (escalate)      (ineligible)  (escalate)  (escalate)

Edges are conditional: each node's output status determines the next node.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.redis import AsyncRedisSaver

from refund_agent.agent.nodes import (
    check_eligibility,
    check_magnitude,
    check_velocity,
    escalate,
    execute_refunds,
    grade_evidence,
    resolve_ambiguity,
)
from refund_agent.agent.state import RefundSessionState
from refund_agent.config import get_settings
from refund_agent.models import EscalationReason, EvidenceGrade, RefundStatus

settings = get_settings()


def _after_ambiguity(state: RefundSessionState) -> str:
    if state.get("awaiting_confirmation"):
        return END
    if not state.get("candidate_transactions"):
        return END
    return "check_velocity"


def _after_velocity(state: RefundSessionState) -> str:
    if not state.get("velocity_ok"):
        return "escalate"
    return "check_eligibility"


def _after_eligibility(state: RefundSessionState) -> str:
    if state.get("status") == RefundStatus.INELIGIBLE:
        return END
    if not state.get("eligible_transactions"):
        return END
    return "grade_evidence"


def _after_evidence(state: RefundSessionState) -> str:
    if state.get("awaiting_confirmation"):
        return END

    grade_raw = state.get("evidence_grade")
    if not grade_raw:
        return END

    grade = EvidenceGrade(**grade_raw)

    if grade.requires_human or grade.confidence_score < settings.escalation_threshold:
        return "escalate"

    if grade.confidence_score < settings.confidence_threshold:
        return "escalate"

    return "check_magnitude"


def _after_magnitude(state: RefundSessionState) -> str:
    if not state.get("magnitude_ok"):
        return "escalate"
    return "execute_refunds"


def build_graph(checkpointer: AsyncRedisSaver | None = None) -> StateGraph:
    graph = StateGraph(RefundSessionState)

    graph.add_node("resolve_ambiguity", resolve_ambiguity)
    graph.add_node("check_velocity", check_velocity)
    graph.add_node("check_eligibility", check_eligibility)
    graph.add_node("grade_evidence", grade_evidence)
    graph.add_node("check_magnitude", check_magnitude)
    graph.add_node("execute_refunds", execute_refunds)
    graph.add_node("escalate", escalate)

    graph.add_edge(START, "resolve_ambiguity")

    graph.add_conditional_edges("resolve_ambiguity", _after_ambiguity, {
        END: END,
        "check_velocity": "check_velocity",
    })
    graph.add_conditional_edges("check_velocity", _after_velocity, {
        "escalate": "escalate",
        "check_eligibility": "check_eligibility",
    })
    graph.add_conditional_edges("check_eligibility", _after_eligibility, {
        END: END,
        "grade_evidence": "grade_evidence",
    })
    graph.add_conditional_edges("grade_evidence", _after_evidence, {
        END: END,
        "escalate": "escalate",
        "check_magnitude": "check_magnitude",
    })
    graph.add_conditional_edges("check_magnitude", _after_magnitude, {
        "escalate": "escalate",
        "execute_refunds": "execute_refunds",
    })
    graph.add_edge("execute_refunds", END)
    graph.add_edge("escalate", END)

    if checkpointer:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()


async def get_compiled_graph():
    """Return the compiled graph with Redis checkpointing."""
    from redis.asyncio import from_url as redis_from_url
    redis_client = redis_from_url(settings.redis_url)
    checkpointer = AsyncRedisSaver(redis_client)
    await checkpointer.asetup()
    return build_graph(checkpointer=checkpointer)
