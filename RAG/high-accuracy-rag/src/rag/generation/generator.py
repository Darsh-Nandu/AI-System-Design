"""Constrained generation: Claude only uses the provided context chunks.

The hard system prompt explicitly forbids drawing on training knowledge.
If the context does not contain the answer, the model must say so.
This is the second layer of hallucination prevention.
"""

from __future__ import annotations

import anthropic

from rag.config import get_settings
from rag.logging import get_logger
from rag.models import ScoredChunk

logger = get_logger(__name__)
settings = get_settings()

_SYSTEM = """\
You are a legal research assistant. Answer the user's question using ONLY the provided context chunks.

STRICT RULES:
1. Do not use any knowledge from your training data. Only use information present in the context.
2. If the answer is not contained in the provided context, say explicitly: "The provided documents do not contain sufficient information to answer this question."
3. Cite the source of every claim using the chunk citation provided (format: [DOC_ID | section | p.N]).
4. Do not speculate, infer, or extrapolate beyond what is written in the context.
5. Be precise and concise. Do not pad the answer with general background knowledge."""


def _format_context(chunks: list[ScoredChunk]) -> str:
    parts: list[str] = []
    for i, sc in enumerate(chunks, 1):
        parts.append(
            f"[Context {i}] Citation: {sc.chunk.citation}\n{sc.chunk.text}"
        )
    return "\n\n---\n\n".join(parts)


async def generate_answer(query: str, chunks: list[ScoredChunk]) -> str:
    if not chunks:
        return "The provided documents do not contain sufficient information to answer this question."

    context = _format_context(chunks)
    user_message = f"CONTEXT:\n\n{context}\n\nQUESTION: {query}"

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
    except Exception as exc:
        logger.exception("generation_failed", error=str(exc))
        return "An error occurred while generating the answer. Please try again."
