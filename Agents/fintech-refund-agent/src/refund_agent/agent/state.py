"""LangGraph agent state -- the single source of truth across all nodes."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

from refund_agent.models import (
    EscalationReason,
    EvidenceGrade,
    EvidenceSubmission,
    RefundResult,
    RefundStatus,
    Transaction,
)


class RefundSessionState(TypedDict):
    # Identity
    session_id: str
    user_id: str

    # Conversation history (managed by LangGraph add_messages reducer)
    messages: Annotated[list[BaseMessage], add_messages]

    # Raw user input for the current turn
    user_message: str

    # Stage: ambiguity resolution
    candidate_transactions: list[Transaction]
    confirmed_transaction_ids: list[str]
    awaiting_confirmation: bool

    # Stage: velocity check
    velocity_count_24h: int
    velocity_ok: bool

    # Stage: eligibility
    eligible_transactions: list[Transaction]
    ineligible_reasons: dict[str, str]  # txn_id -> reason

    # Stage: evidence
    evidence: EvidenceSubmission | None
    evidence_grade: EvidenceGrade | None

    # Stage: magnitude
    total_amount: Decimal
    magnitude_ok: bool

    # Stage: execution
    idempotency_keys: dict[str, str]       # txn_id -> SHA256 key
    completed_refunds: list[RefundResult]
    pending_transaction_ids: list[str]
    failed_transaction_ids: list[str]

    # Outcome
    status: RefundStatus
    escalation_reason: EscalationReason | None
    human_ticket_id: str | None

    # Control flow
    next_prompt: str     # message to show the user on next turn
    error: str | None
