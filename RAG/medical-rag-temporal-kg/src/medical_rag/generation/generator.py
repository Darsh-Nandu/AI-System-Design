"""Constrained evidence-grounded generation using Claude."""

from __future__ import annotations

import anthropic
import structlog

from medical_rag.config import get_settings
from medical_rag.models import EvidenceItem

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a clinical decision support AI. Your role is to synthesize medical evidence and provide \
structured clinical analysis.

STRICT RULES:
1. Use ONLY the evidence provided in the EVIDENCE POOL below. Do not draw on your training data.
2. Every factual claim MUST cite its evidence source using [SOURCE_ID].
3. If the evidence does not contain sufficient information to answer the question, \
state explicitly: "The available clinical records do not contain sufficient information to answer this question."
4. Never speculate. Never invent clinical values.
5. Flag any drug interactions or safety concerns clearly with [WARNING].
6. Recommend specialist consultation when evidence suggests it.
7. Always end with: this output requires clinical judgment by a qualified physician.

FORMAT:
- Clinical Summary (2-3 sentences)
- Key Findings (bullet points with citations)
- Safety Concerns (if any)
- Recommended Actions
- Limitations"""


def _format_evidence(evidence: list[EvidenceItem]) -> str:
    lines: list[str] = ["EVIDENCE POOL:"]
    for i, ev in enumerate(evidence):
        tier = ev.tier.value
        lines.append(f"\n[SOURCE_{i+1}] ({tier} confidence, source: {ev.source_type}):")
        lines.append(ev.content[:800])
    return "\n".join(lines)


async def generate_answer(query: str, evidence: list[EvidenceItem]) -> str:
    if not evidence:
        return (
            "The available clinical records do not contain sufficient information to answer this question. "
            "Please ensure patient records have been properly ingested."
        )

    cfg = get_settings()
    client = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)

    evidence_text = _format_evidence(evidence)
    user_message = f"{evidence_text}\n\nCLINICAL QUESTION: {query}"

    try:
        response = await client.messages.create(
            model=cfg.llm_model,
            max_tokens=cfg.llm_max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        answer = response.content[0].text
        log.info("generation_complete", evidence_count=len(evidence), answer_len=len(answer))
        return answer
    except Exception as exc:
        log.error("generation_error", error=str(exc))
        return (
            "Unable to generate clinical analysis due to a system error. "
            "Please contact your system administrator."
        )
