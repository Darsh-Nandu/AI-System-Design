"""CRAG (Corrective RAG) verifier.

Before passing chunks to the generator, this LLM grader checks whether each
chunk actually answers the query. This is the key guard against the model
blending irrelevant retrieved context with its training data.

Grade outcomes:
  RELEVANT   -- pass chunk through
  IRRELEVANT -- discard chunk
  AMBIGUOUS  -- trigger fallback: fetch next-k chunks and try again
"""

from __future__ import annotations

import json
import time

import anthropic

from rag.config import get_settings
from rag.logging import get_logger
from rag.metrics import chunks_passed_crag, chunks_rejected_crag, crag_latency
from rag.models import ChunkRelevance, ScoredChunk

logger = get_logger(__name__)
settings = get_settings()

_SYSTEM = """\
You are a relevance grader for a legal retrieval system.
Given a QUERY and a CHUNK of text, decide if the chunk is relevant to answering the query.

Respond with JSON only:
{"relevance": "relevant" | "irrelevant" | "ambiguous", "reason": "one sentence"}

Rules:
- relevant: the chunk directly contains information that answers the query
- irrelevant: the chunk is about a different topic or does not help answer the query
- ambiguous: the chunk is tangentially related but more context is needed"""


async def verify_chunks(
    query: str,
    chunks: list[ScoredChunk],
) -> list[ScoredChunk]:
    """Return only RELEVANT chunks. AMBIGUOUS ones are kept with a warning."""
    if not chunks:
        return []

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    passed: list[ScoredChunk] = []

    t0 = time.perf_counter()

    for sc in chunks:
        try:
            response = await client.messages.create(
                model=settings.llm_model,
                max_tokens=128,
                system=_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": f"QUERY: {query}\n\nCHUNK:\n{sc.chunk.text[:1500]}",
                    }
                ],
            )
            data = json.loads(response.content[0].text)
            relevance = ChunkRelevance(data.get("relevance", "ambiguous"))
        except Exception as exc:
            logger.warning("crag_verify_failed", error=str(exc))
            relevance = ChunkRelevance.AMBIGUOUS

        sc.relevance = relevance

        if relevance == ChunkRelevance.RELEVANT:
            chunks_passed_crag.inc()
            passed.append(sc)
        elif relevance == ChunkRelevance.AMBIGUOUS:
            chunks_passed_crag.inc()
            passed.append(sc)
            logger.debug("crag_ambiguous", chunk_id=sc.chunk.id)
        else:
            chunks_rejected_crag.inc()
            logger.debug("crag_rejected", chunk_id=sc.chunk.id)

    crag_latency.observe(time.perf_counter() - t0)
    logger.info("crag_verified", total=len(chunks), passed=len(passed))
    return passed
