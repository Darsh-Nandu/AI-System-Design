"""Evidence grading node.

Uses Claude to classify the user's evidence into HIGH / MEDIUM / LOW confidence.
HIGH (system-verifiable) -> auto-approve if score >= threshold
MEDIUM (document-verifiable) -> OCR and compare
LOW (subjective) -> escalate to human agent
"""

from __future__ import annotations

import json

from anthropic import AsyncAnthropic
from langchain_core.messages import AIMessage, HumanMessage

from refund_agent.agent.state import RefundSessionState
from refund_agent.config import get_settings
from refund_agent.logging import get_logger
from refund_agent.metrics import evidence_grades_total
from refund_agent.models import ConfidenceLevel, EvidenceGrade, EvidenceSubmission, Transaction

settings = get_settings()
logger = get_logger(__name__)

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

_SYSTEM_PROMPT = """You are a refund evidence classifier for a fintech company.

Given a user's refund reason and the transactions in question, classify the evidence:

HIGH confidence (system-verifiable, score 0.85-1.0):
- "delivered outside promised date" -- verify against delivery DB
- "duplicate charge" -- verify against transaction DB
- "item never arrived" -- verify against logistics API
- "charged wrong amount" -- verify against order DB

MEDIUM confidence (document-verifiable, score 0.60-0.84):
- "receipt mismatch" -- requires OCR and comparison
- "wrong item description on receipt"
- "subscription already cancelled"

LOW confidence (subjective, score 0.0-0.59):
- "product didn't work as described"
- "changed my mind"
- video or photo evidence of defect
- vague quality complaints

Respond ONLY with a valid JSON object. No prose:
{
  "confidence_level": "high" | "medium" | "low",
  "confidence_score": 0.0 to 1.0,
  "evidence_type": "short_label",
  "reason": "one-sentence explanation",
  "system_verifiable": true | false,
  "requires_human": true | false
}"""


async def grade_evidence(state: RefundSessionState) -> RefundSessionState:
    """Ask the user for their reason, then grade the evidence with Claude."""
    session_id = state["session_id"]
    eligible: list[Transaction] = [Transaction(**t) for t in state["eligible_transactions"]]
    evidence_raw: EvidenceSubmission | None = state.get("evidence")

    # If no evidence yet, prompt the user
    if not evidence_raw:
        total = sum(t.amount for t in eligible)
        return {
            **state,
            "next_prompt": (
                f"To process the refund of ${total:.2f}, please describe the reason. "
                "Include any relevant details (e.g. 'item never arrived', 'duplicate charge', "
                "'delivered 5 days late')."
            ),
            "awaiting_confirmation": True,
        }

    txn_summary = "\n".join(
        f"- {t.merchant} #{t.id[-6:]} ${t.amount:.2f} ({t.created_at.strftime('%Y-%m-%d')})"
        for t in eligible
    )
    user_content = (
        f"Transactions:\n{txn_summary}\n\n"
        f"Refund reason: {evidence_raw.reason}\n"
        f"Additional details: {evidence_raw.raw_text or 'none'}"
    )

    response = await _client.messages.create(
        model=settings.llm_model,
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text.strip()
    try:
        data = json.loads(raw)
        grade = EvidenceGrade(
            confidence_level=ConfidenceLevel(data["confidence_level"]),
            confidence_score=float(data["confidence_score"]),
            reason=data["reason"],
            system_verifiable=data.get("system_verifiable", False),
            requires_human=data.get("requires_human", False),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("evidence_parse_failed", error=str(exc), raw=raw)
        grade = EvidenceGrade(
            confidence_level=ConfidenceLevel.LOW,
            confidence_score=0.0,
            reason="Could not parse evidence -- escalating to human agent.",
            requires_human=True,
        )

    evidence_grades_total.labels(level=grade.confidence_level.value).inc()
    logger.info(
        "evidence_graded",
        session_id=session_id,
        confidence_level=grade.confidence_level,
        confidence_score=grade.confidence_score,
    )

    evidence_type = data.get("evidence_type", "unclassified") if "data" in dir() else "unclassified"

    return {
        **state,
        "evidence_grade": grade.model_dump(),
        "evidence": {**evidence_raw.model_dump(), "evidence_type": evidence_type},
        "next_prompt": f"Evidence received. Confidence score: {grade.confidence_score:.2f}",
        "messages": state["messages"] + [
            HumanMessage(content=evidence_raw.reason),
            AIMessage(content=f"Evidence received. Confidence score: {grade.confidence_score:.2f}"),
        ],
    }
