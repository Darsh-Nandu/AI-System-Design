"""LLM-powered Document Card generation.

Generates a 200-word summary and extracts structured stats from the full
document text. Used for the Tier-1 index (card-level search).
"""

from __future__ import annotations

import json

import anthropic

from rag.config import get_settings
from rag.logging import get_logger
from rag.models import DocumentCard, RawDocument

logger = get_logger(__name__)
settings = get_settings()

_SYSTEM = """\
You are a legal document analyst. Given a legal document, produce a JSON response with:
  "summary": a factual 150-200 word summary of the key holdings and facts
  "tags": list of 3-8 descriptive tags (snake_case, e.g. data_breach, software_liability)
  "stats": dict of structured facts (e.g. {"ruling": "liable", "damages_usd": 500000, "users_affected": 12000})

Respond with valid JSON only. No prose outside the JSON object."""

_USER_TEMPLATE = """\
Document Name: {name}
Date: {date}
Type: {doc_type}
Jurisdiction: {jurisdiction}

Full Text (truncated to first 6000 characters):
{text}"""


async def generate_document_card(
    doc: RawDocument,
    document_id: str,
    chunk_ids: list[str],
) -> DocumentCard:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    truncated = doc.text[:6000]
    user_msg = _USER_TEMPLATE.format(
        name=doc.name,
        date=doc.date.isoformat(),
        doc_type=doc.doc_type.value,
        jurisdiction=", ".join(doc.jurisdiction),
        text=truncated,
    )

    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=512,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        data = json.loads(response.content[0].text)
        summary = data.get("summary", "")
        tags = data.get("tags", [])
        stats = data.get("stats", {})
    except Exception as exc:
        logger.warning("card_generation_failed", doc=document_id, error=str(exc))
        summary = doc.text[:300]
        tags = doc.tags
        stats = {}

    return DocumentCard(
        id=document_id,
        name=doc.name,
        date=doc.date,
        doc_type=doc.doc_type,
        jurisdiction=doc.jurisdiction or [doc.country_code, doc.state_code],
        tags=list(set(doc.tags + tags)),
        summary=summary,
        stats=stats,
        chunk_ids=chunk_ids,
        version=doc.version,
    )
