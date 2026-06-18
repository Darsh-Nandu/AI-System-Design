# High-Accuracy RAG System

> Legal document retrieval for 500,000 documents with hallucination prevention and explainable citations.

**Domain:** Legal, compliance, finance -- any domain where hallucination has serious consequences
**Reference systems:** Harvey AI, Casetext, Westlaw AI

---

## Why Standard RAG Fails Here

1. Semantic search retrieves *related* content, not *correct* content for structured queries
2. The LLM blends retrieved context with training data, producing hallucinated citations
3. Amended documents leave stale chunks in the index

This system addresses all three.

---

## Architecture

```
Query
  |
  v
[Query Decomposition]
  LLM breaks "software company liable for breach affecting 10k+ users"
  into sub-queries: entity_type, event_type, scale_filter (structured)
  |
  v
[Metadata Pre-Filter]
  Filter by jurisdiction, date range, doc_type -- no vector search yet
  |
  v
[Two-Tier Index Search]
  Tier 1: Document Card index (summary embeddings) -- narrows 500k to ~50 docs
  Tier 2: Chunk index -- only within matched document cards
  |
  v
[Cross-Encoder Re-ranker]
  ms-marco-MiniLM scores each chunk against original query
  Low-scoring chunks discarded
  |
  v
[CRAG Verifier]
  LLM grades each remaining chunk: relevant / irrelevant / ambiguous
  Ambiguous triggers fallback (next-k chunks)
  |
  v
[Constrained Generation]
  Hard system prompt: "Only use provided context. If answer not present, say so."
  |
  v
[Faithfulness Checker]
  Every claim mapped to a source chunk via cosine similarity
  Ungrounded claims flagged or removed
  |
  v
Answer + Citations (doc ID, page, section)
```

---

## Two-Tier Indexing

Each document gets a **Document Card** in Qdrant at the summary level:

```json
{
  "id": "IN:MH:MUM:2019:CR:4821:v1",
  "name": "Tata Consultancy vs SEBI",
  "date": "2019-03-14",
  "doc_type": "case_law",
  "jurisdiction": ["IN", "MH"],
  "tags": ["data_breach", "software_liability"],
  "summary": "TCS held liable for...",
  "stats": {"ruling": "liable", "damages_crore": 12.5, "users_affected": 45000},
  "chunk_ids": ["IN:MH:MUM:2019:CR:4821:v1:0001", "..."]
}
```

Search narrows from 500,000 documents to ~50 before ever searching chunks.

---

## Deterministic Document IDs

Format: `{country}:{state}:{district}:{year}:{doc_type}:{serial}:v{version}`

Why this matters:
- Upsert-based ingestion: amended documents replace old ones atomically
- Namespace filtering: `IN:MH:*` without extra metadata overhead
- Full audit trail: every version retained, only latest version is searched

---

## Hallucination Prevention -- Three Layers

| Layer | Mechanism |
|---|---|
| Retrieval grounding | CRAG verifier rejects chunks that do not answer the query |
| Constrained generation | Hard system prompt: model cannot use external knowledge |
| Faithfulness check | Every output sentence mapped to a source chunk; ungrounded claims flagged |

---

## Freshness

Daily ingestion pipeline:
1. Schema validation + duplicate detection
2. PII check (Presidio) -- anonymize before storage
3. Parse, chunk, embed, generate Document Card
4. Upsert by deterministic ID -- old chunks deleted atomically
5. Alert if any document type has not updated in 24h

---

## Quick Start

```bash
docker compose up -d
make install
python -m example.seed_documents
python -m example.run_query "software company liable for data breach affecting more than 10000 users"
open http://localhost:8084/docs
```

---

## Project Structure

```
src/rag/
  models.py           -- DocumentCard, DocumentChunk, RAGResponse, DecomposedQuery
  config.py           -- pydantic-settings
  indexing/           -- document ID, chunker, embedder, card generator, ingestion pipeline, PII
  retrieval/          -- metadata filter, two-tier search, cross-encoder reranker, CRAG verifier
  generation/         -- constrained generator, faithfulness checker
  pipeline/           -- query decomposer, full query pipeline
  storage/            -- Qdrant client, Postgres document registry
  monitoring/         -- freshness alerts
  api/                -- FastAPI query + document management endpoints
```

---

## Tools

| Component | Tool |
|---|---|
| Vector store | Qdrant (two collections: cards + chunks) |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 |
| Re-ranking | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| PII detection | Microsoft Presidio |
| LLM | Anthropic Claude (claude-sonnet-4-6) |
| Storage | PostgreSQL 16 via SQLAlchemy 2.0 async |
| Observability | Prometheus + Grafana + structlog |
