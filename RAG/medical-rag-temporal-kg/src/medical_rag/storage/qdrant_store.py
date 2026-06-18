"""Qdrant vector store for medical findings and patient timelines."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from sentence_transformers import SentenceTransformer

from medical_rag.config import get_settings
from medical_rag.models import EvidenceItem, ConfidenceTier, MedicalFinding, PatientTimeline

log = structlog.get_logger(__name__)

_client: AsyncQdrantClient | None = None
_model: SentenceTransformer | None = None
_executor = ThreadPoolExecutor(max_workers=2)


def _get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        cfg = get_settings()
        _client = AsyncQdrantClient(url=cfg.qdrant_url)
    return _client


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        cfg = get_settings()
        _model = SentenceTransformer(cfg.embedding_model)
    return _model


def _embed(text: str) -> list[float]:
    import asyncio
    loop = asyncio.get_event_loop()
    future = loop.run_in_executor(_executor, lambda: _get_model().encode(text).tolist())
    return future  # type: ignore[return-value]


def _stable_id(text: str) -> int:
    digest = hashlib.md5(text.encode()).digest()
    return abs(int.from_bytes(digest[:8], "big")) % (2**63)


async def embed_async(text: str) -> list[float]:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, lambda: _get_model().encode(text).tolist())


async def initialize_collections() -> None:
    cfg = get_settings()
    client = _get_client()
    dim = cfg.qdrant_embedding_dim

    for coll in [cfg.qdrant_findings_collection, cfg.qdrant_timelines_collection]:
        try:
            await client.get_collection(coll)
        except Exception:
            await client.create_collection(
                collection_name=coll,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            log.info("qdrant_collection_created", collection=coll)


async def index_finding(finding: MedicalFinding) -> None:
    client = _get_client()
    cfg = get_settings()

    text = _build_finding_text(finding)
    vector = await embed_async(text)

    payload: dict[str, Any] = {
        "finding_id": finding.finding_id,
        "patient_id": finding.patient_id,
        "modality": finding.modality.value,
        "finding_date": finding.finding_date.isoformat(),
        "is_abnormal": finding.is_abnormal,
        "severity": finding.severity.value,
        "specialist_flags": finding.specialist_flags,
        "confidence": finding.confidence,
        "text": text,
    }

    point = PointStruct(
        id=_stable_id(finding.finding_id),
        vector=vector,
        payload=payload,
    )
    await client.upsert(collection_name=cfg.qdrant_findings_collection, points=[point])


def _build_finding_text(finding: MedicalFinding) -> str:
    parts = [finding.raw_text or ""]
    for entity in finding.entities:
        parts.append(f"{entity.entity_type}: {entity.value}")
    for lr in finding.lab_results:
        abnormal = " [ABNORMAL]" if lr.is_abnormal else ""
        parts.append(f"{lr.test_name}: {lr.value} {lr.unit}{abnormal}")
    return " | ".join(p for p in parts if p)[:2000]


async def search_findings(
    query: str,
    patient_id: str,
    top_k: int = 10,
) -> list[EvidenceItem]:
    client = _get_client()
    cfg = get_settings()
    vector = await embed_async(query)

    results = await client.search(
        collection_name=cfg.qdrant_findings_collection,
        query_vector=vector,
        limit=top_k,
        query_filter=Filter(
            must=[FieldCondition(key="patient_id", match=MatchValue(value=patient_id))]
        ),
        with_payload=True,
    )

    evidence: list[EvidenceItem] = []
    for r in results:
        payload = r.payload or {}
        score = float(r.score)
        tier = (
            ConfidenceTier.HIGH if score >= cfg.high_confidence_threshold
            else ConfidenceTier.MEDIUM if score >= cfg.medium_confidence_threshold
            else ConfidenceTier.LOW
        )
        evidence.append(EvidenceItem(
            source_type="vector_search",
            source_id=payload.get("finding_id", ""),
            content=payload.get("text", ""),
            confidence=score,
            tier=tier,
            specialist_flags=payload.get("specialist_flags", []),
        ))
    return evidence


async def index_timeline(timeline: PatientTimeline, summary_text: str) -> None:
    client = _get_client()
    cfg = get_settings()

    vector = await embed_async(summary_text)
    point = PointStruct(
        id=_stable_id(f"timeline:{timeline.patient_id}"),
        vector=vector,
        payload={
            "patient_id": timeline.patient_id,
            "finding_count": len(timeline.findings),
            "summary": summary_text[:1000],
        },
    )
    await client.upsert(collection_name=cfg.qdrant_timelines_collection, points=[point])


async def search_similar_timelines(
    query_text: str, exclude_patient: str, top_k: int = 5
) -> list[dict[str, Any]]:
    client = _get_client()
    cfg = get_settings()
    vector = await embed_async(query_text)

    results = await client.search(
        collection_name=cfg.qdrant_timelines_collection,
        query_vector=vector,
        limit=top_k + 1,
        with_payload=True,
    )

    return [
        {"score": r.score, **r.payload}
        for r in results
        if r.payload and r.payload.get("patient_id") != exclude_patient
    ][:top_k]
