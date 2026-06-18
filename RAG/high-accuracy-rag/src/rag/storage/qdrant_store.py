"""Qdrant client wrapper managing the two-tier index.

Collection 1: legal_document_cards   -- one vector per document (summary embedding)
Collection 2: legal_chunks           -- one vector per chunk
"""

from __future__ import annotations

from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from rag.config import get_settings
from rag.logging import get_logger
from rag.models import DocumentCard, DocumentChunk

logger = get_logger(__name__)
settings = get_settings()


class QdrantStore:
    def __init__(self) -> None:
        self._client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )

    async def ensure_collections(self) -> None:
        """Create collections if they do not exist."""
        existing = {c.name for c in (await self._client.get_collections()).collections}

        if settings.card_collection not in existing:
            await self._client.create_collection(
                collection_name=settings.card_collection,
                vectors_config=qmodels.VectorParams(
                    size=settings.embedding_dim,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            await self._client.create_payload_index(
                collection_name=settings.card_collection,
                field_name="jurisdiction",
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
            await self._client.create_payload_index(
                collection_name=settings.card_collection,
                field_name="doc_type",
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
            await self._client.create_payload_index(
                collection_name=settings.card_collection,
                field_name="tags",
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
            logger.info("collection_created", name=settings.card_collection)

        if settings.chunk_collection not in existing:
            await self._client.create_collection(
                collection_name=settings.chunk_collection,
                vectors_config=qmodels.VectorParams(
                    size=settings.embedding_dim,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            await self._client.create_payload_index(
                collection_name=settings.chunk_collection,
                field_name="document_id",
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
            logger.info("collection_created", name=settings.chunk_collection)

    async def upsert_card(self, card: DocumentCard, embedding: list[float]) -> None:
        await self._client.upsert(
            collection_name=settings.card_collection,
            points=[
                qmodels.PointStruct(
                    id=_stable_id(card.id),
                    vector=embedding,
                    payload={
                        "doc_id": card.id,
                        "name": card.name,
                        "date": card.date.isoformat(),
                        "doc_type": card.doc_type.value,
                        "jurisdiction": card.jurisdiction,
                        "tags": card.tags,
                        "summary": card.summary,
                        "stats": card.stats,
                        "chunk_ids": card.chunk_ids,
                        "version": card.version,
                    },
                )
            ],
        )

    async def upsert_chunks(
        self, chunks: list[DocumentChunk], embeddings: list[list[float]]
    ) -> None:
        points = [
            qmodels.PointStruct(
                id=_stable_id(chunk.id),
                vector=emb,
                payload={
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "section": chunk.section,
                    "page": chunk.page,
                    "chunk_index": chunk.chunk_index,
                },
            )
            for chunk, emb in zip(chunks, embeddings)
        ]
        # Upsert in batches of 100
        for i in range(0, len(points), 100):
            await self._client.upsert(
                collection_name=settings.chunk_collection,
                points=points[i : i + 100],
            )

    async def delete_document_chunks(self, document_id: str) -> None:
        """Remove all chunks belonging to a document (for atomic replacement)."""
        await self._client.delete(
            collection_name=settings.chunk_collection,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id",
                            match=qmodels.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )

    async def search_cards(
        self,
        query_vector: list[float],
        metadata_filter: dict[str, Any] | None = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        qdrant_filter = _build_filter(metadata_filter)
        results = await self._client.search(
            collection_name=settings.card_collection,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )
        return [r.payload for r in results if r.payload]

    async def search_chunks_in_documents(
        self,
        query_vector: list[float],
        document_ids: list[str],
        top_k: int = 50,
    ) -> list[tuple[dict[str, Any], float]]:
        """Search only within chunks belonging to the given document IDs."""
        if not document_ids:
            return []

        qdrant_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="document_id",
                    match=qmodels.MatchAny(any=document_ids),
                )
            ]
        )
        results = await self._client.search(
            collection_name=settings.chunk_collection,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )
        return [(r.payload, r.score) for r in results if r.payload]


def _stable_id(text_id: str) -> int:
    """Convert a string ID to a stable positive integer for Qdrant."""
    import hashlib
    h = hashlib.md5(text_id.encode()).digest()
    return int.from_bytes(h[:8], "big") % (2**63)


def _build_filter(metadata_filter: dict[str, Any] | None) -> qmodels.Filter | None:
    if not metadata_filter:
        return None

    conditions: list[qmodels.Condition] = []

    for key, value in metadata_filter.items():
        if isinstance(value, list):
            conditions.append(
                qmodels.FieldCondition(key=key, match=qmodels.MatchAny(any=value))
            )
        elif isinstance(value, dict) and ("gte" in value or "lte" in value):
            conditions.append(
                qmodels.FieldCondition(
                    key=key,
                    range=qmodels.Range(
                        gte=value.get("gte"),
                        lte=value.get("lte"),
                    ),
                )
            )
        else:
            conditions.append(
                qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value))
            )

    return qmodels.Filter(must=conditions) if conditions else None
