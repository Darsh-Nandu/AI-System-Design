"""Two-tier retrieval: Document Card search -> Chunk search within matched cards.

Stage 1: Embed the query, apply metadata pre-filter, search Card summaries.
         Narrows 500k documents to ~50.
Stage 2: Search only within chunks belonging to the top-K cards.
         Much faster and more precise than searching all 10M+ chunks.
"""

from __future__ import annotations

from typing import Any

from rag.config import get_settings
from rag.indexing.embedder import embed_one
from rag.logging import get_logger
from rag.metrics import chunks_retrieved
from rag.models import DocumentChunk, ScoredChunk
from rag.storage.qdrant_store import QdrantStore

logger = get_logger(__name__)
settings = get_settings()


class TwoTierSearch:
    def __init__(self) -> None:
        self._store = QdrantStore()

    async def search(
        self,
        query: str,
        metadata_filter: dict[str, Any] | None = None,
        card_top_k: int | None = None,
        chunk_top_k: int | None = None,
    ) -> list[ScoredChunk]:
        card_k = card_top_k or settings.card_top_k
        chunk_k = chunk_top_k or settings.chunk_top_k

        query_embedding = await embed_one(query)

        # Tier 1: search document cards
        cards = await self._store.search_cards(
            query_vector=query_embedding,
            metadata_filter=metadata_filter,
            top_k=card_k,
        )

        if not cards:
            logger.info("no_cards_matched", query=query[:80])
            return []

        # Collect all document IDs from matched cards
        document_ids: list[str] = []
        for card in cards:
            doc_id = card.get("doc_id", "")
            if doc_id:
                document_ids.append(doc_id)

        logger.info("tier1_matched", card_count=len(document_ids))

        # Tier 2: search chunks within matched documents only
        raw_chunks = await self._store.search_chunks_in_documents(
            query_vector=query_embedding,
            document_ids=document_ids,
            top_k=chunk_k,
        )

        chunks_retrieved.inc(len(raw_chunks))

        results: list[ScoredChunk] = []
        for payload, score in raw_chunks:
            chunk = DocumentChunk(
                id=payload.get("chunk_id", ""),
                document_id=payload.get("document_id", ""),
                text=payload.get("text", ""),
                section=payload.get("section", ""),
                page=payload.get("page"),
                chunk_index=payload.get("chunk_index", 0),
            )
            results.append(ScoredChunk(chunk=chunk, score=score))

        return results
