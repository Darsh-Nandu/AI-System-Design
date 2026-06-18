"""Query decomposition: breaks complex natural language queries into sub-queries.

A single embedding often misses multi-constraint queries.
Example: "software company liable for data breach affecting more than 10000 users"
becomes:
  - sub-query 1: "software technology company defendant" {doc_type: case_law}
  - sub-query 2: "data breach cybersecurity incident"
  - sub-query 3: structured filter {stats.users_affected: {gte: 10000}}

The decomposer also flags if the query is too vague and needs clarification.
"""

from __future__ import annotations

import json

import anthropic

from rag.config import get_settings
from rag.logging import get_logger
from rag.models import DecomposedQuery, SubQuery

logger = get_logger(__name__)
settings = get_settings()

_SYSTEM = """\
You are a legal search query analyst. Decompose a natural language query into structured sub-queries for a legal document retrieval system.

Respond with JSON only:
{
  "sub_queries": [
    {"text": "the semantic search query text", "metadata_filters": {"key": "value"}}
  ],
  "clarification_needed": true | false,
  "clarification_reason": "null or reason if clarification_needed is true"
}

metadata_filters can include:
  doc_type: "case_law" | "statute" | "regulation" | "contract" | "advisory"
  jurisdiction: ["IN", "MH"]  (list of jurisdiction codes)
  tags: ["data_breach", ...]  (list of topic tags)
  date: {"gte": "YYYY-MM-DD", "lte": "YYYY-MM-DD"}

Rules:
- Generate 1-4 sub-queries that together cover the full original query
- Use metadata_filters only when the original query explicitly specifies them
- Set clarification_needed=true if the query is too vague to produce useful results
- Keep sub-query text focused and specific"""


async def decompose_query(query: str) -> DecomposedQuery:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=512,
            system=_SYSTEM,
            messages=[{"role": "user", "content": f"Query: {query}"}],
        )
        data = json.loads(response.content[0].text)
        sub_queries = [SubQuery(**sq) for sq in data.get("sub_queries", [])]
        return DecomposedQuery(
            original=query,
            sub_queries=sub_queries or [SubQuery(text=query)],
            clarification_needed=data.get("clarification_needed", False),
            clarification_reason=data.get("clarification_reason"),
        )
    except Exception as exc:
        logger.warning("query_decomposition_failed", error=str(exc))
        return DecomposedQuery(
            original=query,
            sub_queries=[SubQuery(text=query)],
        )
