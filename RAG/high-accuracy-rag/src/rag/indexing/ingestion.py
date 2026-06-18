"""Full document ingestion pipeline.

Steps:
1. Validate schema
2. PII detection and anonymization
3. Generate deterministic document ID
4. Chunk the document
5. Embed all chunks
6. Generate Document Card (LLM summary + stats)
7. Embed Card summary
8. Upsert into Qdrant (delete old chunks atomically, insert new ones)
9. Update Postgres document registry
"""

from __future__ import annotations

from rag.indexing.chunker import chunk_document
from rag.indexing.document_card import generate_document_card
from rag.indexing.document_id import make_document_id
from rag.indexing.embedder import embed_one, embed_texts
from rag.indexing.pii import detect_and_anonymize
from rag.logging import get_logger
from rag.metrics import ingestion_total
from rag.models import IngestionResult, RawDocument
from rag.storage.postgres import AsyncSessionLocal, DocumentRegistryORM
from rag.storage.qdrant_store import QdrantStore

logger = get_logger(__name__)


class IngestionPipeline:
    def __init__(self) -> None:
        self._store = QdrantStore()

    async def ingest(self, doc: RawDocument) -> IngestionResult:
        document_id = make_document_id(doc)
        logger.info("ingestion_started", document_id=document_id)

        try:
            # PII anonymization
            clean_text, pii_count = detect_and_anonymize(doc.text)

            # Chunking
            chunks = chunk_document(document_id, clean_text)

            # Embed all chunks in one batch
            chunk_texts = [c.text for c in chunks]
            chunk_embeddings = await embed_texts(chunk_texts)

            # Upsert chunks: delete old version chunks first
            await self._store.delete_document_chunks(document_id)
            await self._store.upsert_chunks(chunks, chunk_embeddings.tolist())

            # Generate and embed Document Card
            chunk_ids = [c.id for c in chunks]
            card = await generate_document_card(doc, document_id, chunk_ids)
            card_embedding = await embed_one(card.summary)
            await self._store.upsert_card(card, card_embedding)

            # Update Postgres registry
            await _update_registry(document_id, doc, len(chunks))

            ingestion_total.labels(status="success").inc()
            logger.info("ingestion_completed", document_id=document_id, chunks=len(chunks))

            return IngestionResult(
                document_id=document_id,
                success=True,
                chunk_count=len(chunks),
                pii_entities_found=pii_count,
            )

        except Exception as exc:
            ingestion_total.labels(status="failed").inc()
            logger.exception("ingestion_failed", document_id=document_id, error=str(exc))
            return IngestionResult(
                document_id=document_id,
                success=False,
                error=str(exc),
            )


async def _update_registry(document_id: str, doc: RawDocument, chunk_count: int) -> None:
    from datetime import datetime, timezone

    async with AsyncSessionLocal() as db:
        existing = await db.get(DocumentRegistryORM, document_id)
        if existing:
            existing.version = doc.version
            existing.chunk_count = chunk_count
            existing.updated_at = datetime.now(timezone.utc)
        else:
            orm = DocumentRegistryORM(
                id=document_id,
                name=doc.name,
                doc_type=doc.doc_type.value,
                version=doc.version,
                chunk_count=chunk_count,
            )
            db.add(orm)
        await db.commit()
