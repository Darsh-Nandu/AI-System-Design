"""Chat endpoint -- drives the LangGraph agent turn by turn."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from refund_agent.agent.graph import get_compiled_graph
from refund_agent.api.schemas import (
    ChatRequest,
    ChatResponse,
    ConfirmRequest,
    EvidenceRequest,
)
from refund_agent.logging import get_logger
from refund_agent.models import EvidenceSubmission

router = APIRouter(prefix="/chat", tags=["agent"])
logger = get_logger(__name__)


def _get_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


@router.post("/start", response_model=ChatResponse)
async def start_session(request: ChatRequest) -> ChatResponse:
    """Start a new refund session or resume an existing one."""
    session_id = request.session_id or str(uuid.uuid4())
    graph = await get_compiled_graph()
    config = _get_config(session_id)

    initial_state = {
        "session_id": session_id,
        "user_id": request.user_id,
        "messages": [HumanMessage(content=request.message)],
        "user_message": request.message,
        "candidate_transactions": [],
        "confirmed_transaction_ids": [],
        "awaiting_confirmation": False,
        "velocity_count_24h": 0,
        "velocity_ok": False,
        "eligible_transactions": [],
        "ineligible_reasons": {},
        "evidence": None,
        "evidence_grade": None,
        "total_amount": 0,
        "magnitude_ok": False,
        "idempotency_keys": {},
        "completed_refunds": [],
        "pending_transaction_ids": [],
        "failed_transaction_ids": [],
        "status": "pending_confirmation",
        "escalation_reason": None,
        "human_ticket_id": None,
        "next_prompt": "",
        "error": None,
    }

    result = await graph.ainvoke(initial_state, config=config)
    logger.info("chat_turn", session_id=session_id, status=result.get("status"))

    return ChatResponse(
        session_id=session_id,
        message=result.get("next_prompt", ""),
        status=result.get("status", "pending_confirmation"),
        awaiting_input=result.get("awaiting_confirmation", False),
    )


@router.post("/confirm", response_model=ChatResponse)
async def confirm_selection(request: ConfirmRequest) -> ChatResponse:
    """User confirms which transactions they want refunded."""
    graph = await get_compiled_graph()
    config = _get_config(request.session_id)

    state = await graph.aget_state(config)
    if not state or not state.values:
        raise HTTPException(status_code=404, detail="Session not found")

    current = state.values
    candidates = current.get("candidate_transactions") or []

    if request.selection.lower() == "all":
        confirmed_ids = [t["id"] for t in candidates]
    else:
        try:
            indices = [int(x.strip()) - 1 for x in request.selection.split(",")]
            confirmed_ids = [candidates[i]["id"] for i in indices if 0 <= i < len(candidates)]
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Invalid selection. Use 'all' or '1,2,3'")

    if not confirmed_ids:
        raise HTTPException(status_code=400, detail="No valid transactions selected")

    updated_state = {
        **current,
        "confirmed_transaction_ids": confirmed_ids,
        "awaiting_confirmation": False,
        "user_message": request.selection,
    }

    result = await graph.ainvoke(updated_state, config=config)

    return ChatResponse(
        session_id=request.session_id,
        message=result.get("next_prompt", ""),
        status=result.get("status", ""),
        awaiting_input=result.get("awaiting_confirmation", False),
    )


@router.post("/evidence", response_model=ChatResponse)
async def submit_evidence(request: EvidenceRequest) -> ChatResponse:
    """User submits evidence for their refund request."""
    graph = await get_compiled_graph()
    config = _get_config(request.session_id)

    state = await graph.aget_state(config)
    if not state or not state.values:
        raise HTTPException(status_code=404, detail="Session not found")

    current = state.values
    evidence = EvidenceSubmission(
        reason=request.reason,
        raw_text=request.details,
        attachments=request.attachments,
    )

    updated_state = {
        **current,
        "evidence": evidence.model_dump(),
        "awaiting_confirmation": False,
        "user_message": request.reason,
    }

    result = await graph.ainvoke(updated_state, config=config)

    return ChatResponse(
        session_id=request.session_id,
        message=result.get("next_prompt", ""),
        status=result.get("status", ""),
        awaiting_input=False,
    )
