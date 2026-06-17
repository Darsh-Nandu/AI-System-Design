"""Ambiguity resolution node.

Parses vague user intent with Claude, queries the transaction DB,
and returns a structured list for user confirmation.
Rule: never execute on a vague bulk command.
"""

from __future__ import annotations

import json

from anthropic import AsyncAnthropic
from langchain_core.messages import HumanMessage, AIMessage

from refund_agent.agent.state import RefundSessionState
from refund_agent.config import get_settings
from refund_agent.logging import get_logger
from refund_agent.services.transactions import TransactionService

settings = get_settings()
logger = get_logger(__name__)

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

_SYSTEM_PROMPT = """You are a refund assistant for a fintech company.
Your job is to parse the user's refund request and extract:
1. The time range they are referring to (e.g. "last month", "last 30 days", "January")
2. Whether they want ALL transactions or specific ones
3. Any filters they mentioned (merchant name, amount range, etc.)

Respond ONLY with a valid JSON object. No prose. Example:
{
  "time_range_days": 30,
  "want_all": true,
  "merchant_filter": null,
  "min_amount": null,
  "max_amount": null,
  "clarification_needed": false,
  "clarification_question": null
}

If the request is too ambiguous to parse at all, set clarification_needed to true
and provide a clarification_question."""


async def resolve_ambiguity(state: RefundSessionState) -> RefundSessionState:
    """Parse the user message and fetch matching transactions for confirmation."""
    user_message = state["user_message"]
    user_id = state["user_id"]
    session_id = state["session_id"]

    logger.info("ambiguity_resolution_start", session_id=session_id, user_id=user_id)

    response = await _client.messages.create(
        model=settings.llm_model,
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("ambiguity_parse_failed", raw=raw)
        return {
            **state,
            "next_prompt": "I had trouble understanding your request. Could you be more specific about which transactions you'd like refunded?",
            "awaiting_confirmation": True,
        }

    if parsed.get("clarification_needed"):
        return {
            **state,
            "next_prompt": parsed.get("clarification_question", "Could you clarify which transactions you want refunded?"),
            "awaiting_confirmation": True,
        }

    time_range_days: int = parsed.get("time_range_days", 30)
    merchant_filter: str | None = parsed.get("merchant_filter")

    txn_service = TransactionService()
    candidates = await txn_service.get_eligible_transactions(
        user_id=user_id,
        days=time_range_days,
        merchant_filter=merchant_filter,
    )

    if not candidates:
        return {
            **state,
            "candidate_transactions": [],
            "next_prompt": f"I didn't find any refund-eligible transactions from the last {time_range_days} days.",
            "awaiting_confirmation": False,
            "status": "ineligible",
        }

    total = sum(t.amount for t in candidates)
    lines = "\n".join(
        f"{i+1}. {t.merchant} #{t.id[-6:]} - ${t.amount:.2f} - {t.created_at.strftime('%b %d')}"
        for i, t in enumerate(candidates)
    )
    prompt = (
        f"I found {len(candidates)} refund-eligible transaction(s) totalling ${total:.2f}:\n\n"
        f"{lines}\n\n"
        "Reply with the numbers you'd like to refund (e.g. '1, 3') or 'all' to refund everything listed."
    )

    logger.info(
        "ambiguity_resolved",
        session_id=session_id,
        candidate_count=len(candidates),
        total=str(total),
    )

    return {
        **state,
        "candidate_transactions": [t.model_dump() for t in candidates],
        "next_prompt": prompt,
        "awaiting_confirmation": True,
        "messages": state["messages"] + [
            HumanMessage(content=user_message),
            AIMessage(content=prompt),
        ],
    }
