"""Qdrant vector store — collections per partition tier."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from news_aggregator.config import get_settings
from news_aggregator.models import Article, DedupResult, PartitionTier

settings = get_settings()

COLLECTION_MAP: dict[PartitionTier, str] = {
    PartitionTier.HOT: settings.qdrant_collection_hot,
    PartitionTier.WARM: settings.qdrant_collection_warm,
    PartitionTier.COLD: settings.qdrant_collection_cold,
}


@dataclass
class SimilarityMatch:
    article_id: uuid.UUID
    score: float
    is_stale: bool
    story_id: uuid.UUID | None


class QdrantStore:
    def __init__(self) -> None:
        self._client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )

    async def ensure_collections(self) -> None:
        for collection_name in COLLECTION_MAP.values():
            exists = await self._client.collection_exists(collection_name)
            if not exists:
                await self._client.create_collection(
                    collection_name=collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=settings.embedding_dim,
                        distance=qmodels.Distance.COSINE,
                    ),
                    optimizers_config=qmodels.OptimizersConfigDiff(
                        indexing_threshold=20_000,
                    ),
                    hnsw_config=qmodels.HnswConfigDiff(
                        m=16,
                        ef_construct=100,
                    ),
                )

    def _collection_for(self, partition: PartitionTier) -> str:
        return COLLECTION_MAP[partition]

    async def upsert(self, article: Article) -> None:
        collection = self._collection_for(article.partition)
        await self._client.upsert(
            collection_name=collection,
            points=[
                qmodels.PointStruct(
                    id=str(article.id),
                    vector=article.embedding if hasattr(article, "embedding") else [],
                    payload={
                        "url": article.url,
                        "source": article.source,
                        "title": article.title,
                        "entity_fingerprint": article.entity_fingerprint,
                        "topics": article.topics,
                        "is_volatile": article.is_volatile,
                        "stale": article.stale,
                        "story_id": str(article.story_id) if article.story_id else None,
                        "published_at": article.published_at.isoformat(),
                        "processed_at": article.processed_at.isoformat(),
                    },
                )
            ],
        )

    async def search_similar(
        self,
        embedding: list[float],
        partition: PartitionTier,
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[SimilarityMatch]:
        collection = self._collection_for(partition)
        threshold = score_threshold or settings.dedup_cluster_threshold

        results = await self._client.search(
            collection_name=collection,
            query_vector=embedding,
            limit=limit,
            score_threshold=threshold,
            with_payload=True,
        )

        matches = []
        for r in results:
            payload = r.payload or {}
            matches.append(
                SimilarityMatch(
                    article_id=uuid.UUID(str(r.id)),
                    score=r.score,
                    is_stale=payload.get("stale", False),
                    story_id=uuid.UUID(payload["story_id"]) if payload.get("story_id") else None,
                )
            )
        return matches

    async def search_by_entities(
        self,
        embedding: list[float],
        entity_fingerprints: list[str],
        partition: PartitionTier,
    ) -> list[SimilarityMatch]:
        """Entity-pre-filtered similarity search (Stage 1 + Stage 2 combined)."""
        collection = self._collection_for(partition)
        results = await self._client.search(
            collection_name=collection,
            query_vector=embedding,
            limit=20,
            score_threshold=settings.dedup_cluster_threshold,
            query_filter=qmodels.Filter(
                should=[
                    qmodels.FieldCondition(
                        key="entity_fingerprint",
                        match=qmodels.MatchValue(value=fp),
                    )
                    for fp in entity_fingerprints
                ]
            ),
            with_payload=True,
        )

        matches = []
        for r in results:
            payload = r.payload or {}
            matches.append(
                SimilarityMatch(
                    article_id=uuid.UUID(str(r.id)),
                    score=r.score,
                    is_stale=payload.get("stale", False),
                    story_id=uuid.UUID(payload["story_id"]) if payload.get("story_id") else None,
                )
            )
        return matches

    async def mark_stale(self, article_id: uuid.UUID, partition: PartitionTier) -> None:
        collection = self._collection_for(partition)
        await self._client.set_payload(
            collection_name=collection,
            payload={"stale": True},
            points=[str(article_id)],
        )

    async def get_collection_size(self, partition: PartitionTier) -> int:
        collection = self._collection_for(partition)
        info = await self._client.get_collection(collection)
        return info.points_count or 0

    async def close(self) -> None:
        await self._client.close()
