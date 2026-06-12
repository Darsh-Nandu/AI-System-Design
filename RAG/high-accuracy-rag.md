# High-Accuracy RAG System Design

**Domain:** Legal, compliance, finance - any domain where hallucination has serious consequences  
**Interview question:** *"Design a RAG system for a law firm with 500,000 legal documents. It must be accurate, up to date, and explainable."*  
**Industry reference:** Harvey AI, Casetext, Westlaw AI

---

## The Core Problem

Standard RAG fails in high-accuracy domains for three reasons:

1. Semantic search retrieves *related* content, not necessarily *correct* content for structured queries
2. The LLM can blend retrieved content with its training data, producing hallucinated citations
3. New and amended documents can leave stale chunks in the index

This design addresses all three.

---

## Architecture Overview

```
Query
  │
  ▼
[Query Decomposition]
  │  breaks "software company liable for data breach affecting 10,000+ users"
  │  into 3 sub-queries: entity_type, event_type, scale_filter
  ▼
[Metadata Pre-Filter]
  │  filters by jurisdiction, date range, document type
  │  using structured fields - no vector search yet
  ▼
[Two-Tier Index Search]
  │  Tier 1: Document Card index (summary-level embeddings)
  │  Tier 2: Chunk index within matched documents only
  ▼
[Similarity Gate]
  │  cosine similarity check between retrieved chunks
  │  high similarity → skip LLM judge, pass directly
  │  divergent chunks → send to re-ranker
  ▼
[Cross-Encoder Re-ranker]
  │  scores each chunk for relevance to original query
  │  filters out low-scoring chunks
  ▼
[CRAG Verifier LLM]
  │  checks: is this chunk actually answering the query?
  │  grades: relevant / irrelevant / ambiguous
  │  on ambiguous → triggers fallback (expand search or next-k chunks)
  ▼
[Constrained Generation]
  │  system prompt: "Only use information in the provided context.
  │   If the answer is not present, say so explicitly."
  ▼
[Faithfulness Checker]
  │  every claim in output mapped back to a source chunk
  │  unmapped claims → flagged or removed
  ▼
Answer + Citations (page, section, document ID)
```

---

## Two-Tier Indexing (The Key Innovation)

Each document gets a **Document Card** stored at the top level:

```
Document Card {
  id: "IN:MH:MUM:2019:CR:4821"       ← hierarchical deterministic ID
  name: "Tata Consultancy vs SEBI"
  date: "2019-03-14"
  type: "case_law"
  jurisdiction: ["IN", "MH"]
  tags: ["data_breach", "software_liability", "corporate"]
  summary: "TCS held liable for...[200 word summary]"
  stats: { ruling: "liable", damages_crore: 12.5, users_affected: 45000 }
  chunk_ids: ["...001", "...002", ...]   ← pointers to detailed chunks
}
```

Search flow:
1. Filter Document Cards by structured fields (date, jurisdiction, tags)
2. Rank top-K cards by embedding similarity on summary field
3. Only then search chunks - but only within those K documents

This reduces search space from 500,000 documents to ~50, making retrieval faster and more precise.

---

## Deterministic Document IDs

Format: `{country_code}:{state_code}:{district_code}:{year}:{doc_type}:{serial}`

Example: `IN:MH:MUM:2019:CR:4821`

Why this matters:
- **Upsert-based ingestion** - when a document is amended, recompute ID, find existing entry, replace all chunks atomically. No duplicates, no stale chunks.
- **Namespace filtering** - search only Maharashtra cases by filtering `IN:MH:*` without extra metadata overhead
- **Audit trail** - every version of a document is traceable

---

## Query Decomposition

Natural language queries often have multiple constraints that a single embedding misses.

Query: *"software company liable for data breach affecting more than 10,000 users"*

Decomposed into:
- Sub-query 1 (entity): "software technology company defendant"
- Sub-query 2 (event): "data breach cybersecurity incident"  
- Sub-query 3 (filter): `stats.users_affected > 10000` ← structured field, not semantic

Run all three, intersect results. This is why the Document Card's `stats` field matters - scale constraints can be evaluated exactly, not semantically.

---

## Hallucination Prevention - Three Layers

**Layer 1 - Retrieval grounding:** CRAG verifier rejects chunks that don't answer the query. Model never sees irrelevant context to blend from.

**Layer 2 - Constrained generation:** Hard system prompt instruction. Model is explicitly told it cannot use knowledge outside the provided context.

**Layer 3 - Faithfulness check:** Post-generation, every sentence in the output is checked against retrieved chunks using RAGAS faithfulness score. Sentences with no grounding are removed or flagged.

---

## Freshness - Keeping the Index Current

**Daily ingestion pipeline:**
1. New documents arrive → quality gate (schema validation, format check, duplicate detection)
2. PII check (for sensitive filings)
3. Parse → chunk → embed → generate Document Card
4. Upsert by deterministic ID - amended documents automatically replace old versions
5. All chunks from old version are deleted atomically with new version insertion

**Amended document handling:**
- Old ID = `IN:MH:MUM:2019:CR:4821:v1`
- New ID = `IN:MH:MUM:2019:CR:4821:v2`
- Query routing always resolves to latest version by default
- Historical versions retained for audit, not for search

---

## LLM-as-Judge Bias Mitigation

Using an LLM to judge retrieval quality introduces two biases:

**Self-preference bias** - a model similar to the generator will prefer its own style of output.  
Fix: Use a significantly larger model as judge (e.g., if generator is GPT-4, judge with Claude Opus or Gemini Ultra).

**Position bias** - LLM judges prefer whichever answer appears first.  
Fix: Run each judgement twice with swapped order, average the scores.

**Rubric vagueness** - "which is better?" produces inconsistent results.  
Fix: Structured rubric with specific dimensions: factual accuracy (0-3), citation quality (0-3), completeness (0-3), no hallucination (0/1).

---

## Tradeoffs

| Decision | Benefit | Cost |
|---|---|---|
| Two-tier indexing | Faster, more precise search | Higher ingestion complexity |
| Deterministic IDs | Clean upserts, no duplicates | ID schema must be defined upfront |
| CRAG verifier before generation | Filters bad context early | Extra LLM call per query |
| Faithfulness checker after generation | Catches hallucinations | Increases latency by ~300ms |
| Constrained generation | Prevents knowledge blending | Model may say "I don't know" more often |

---

## Failure Modes & Mitigations

**Scanned/image PDFs** - OCR layer (AWS Textract or Tesseract) required before text extraction. Without this, ~30% of legal documents are invisible to the system.

**Query too vague** - "find cases about tech companies" returns too many results. Mitigation: clarification prompt before retrieval if query lacks specific constraints.

**All retrieved chunks are irrelevant** - CRAG verifier rejects everything. Mitigation: fallback to broader search, then inform user "no directly relevant cases found" rather than hallucinating.

**Index staleness** - ingestion pipeline fails silently. Mitigation: monitor last-ingestion timestamp per document type, alert if any type hasn't updated in 24h.

---

## Tools Referenced

| Component | Tool |
|---|---|
| Vector store | Qdrant (metadata filtering + ANN search) |
| Re-ranking | Cohere Rerank or cross-encoder (ms-marco) |
| OCR | AWS Textract |
| Faithfulness check | RAGAS |
| Eval & regression | Braintrust |
| PII detection | Microsoft Presidio |