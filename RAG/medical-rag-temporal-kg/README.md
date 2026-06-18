# Medical RAG with Temporal Knowledge Graph

> Clinical decision support that reasons over a patient's full history -- never hallucinating, always citing sources, HIPAA compliant.

**Domain:** Medical second-opinion, clinical decision support
**Reference:** Google Med-PaLM 2, Microsoft BioGPT, Epic Systems

---

## Why This Is Harder Than Legal RAG

| Problem | Solution |
|---|---|
| Multi-modal inputs (labs, MRI, ECG, text) | Specialist model router per modality |
| Temporal causal reasoning ("kidney declined after drug X") | Neo4j temporal knowledge graph with Cypher traversal |
| Hallucination is life-threatening | Four-layer prevention: specialist models, KG traversal, constrained generation, faithfulness check |
| HIPAA -- maximally sensitive data | Presidio PII removal + date shifting + integrity diff-check + original deletion |

---

## Architecture

```
Doctor uploads patient documents
  |
  v
[PII De-identification Pipeline]
  Presidio NER scan -> identify all PII spans
  Date shift: all dates offset by patient-specific secret delta (preserves temporal gaps)
  Replace: names -> [PATIENT], IDs -> hash, addresses -> city-only
  Integrity diff-check: verify medical values are intact
  Original document deleted from all storage
  |
  v
[Modality Router]
  text report      -> NLP processor (Claude + medical entity extraction)
  lab panel        -> structured lab parser (value, reference range, delta, severity)
  MRI/CT           -> imaging processor stub (Med-SAM interface)
  ECG              -> cardiology processor stub
  All outputs -> MedicalFinding(date, type, confidence, structured data)
  |
  v
[Timeline Construction]
  Chronological sequence of MedicalFinding objects per patient
  Each finding stamped: date, source, confidence, is_abnormal, severity
  |
  v
[Temporal Knowledge Graph -- Neo4j]
  Nodes: Patient, Condition, Drug, LabValue, Procedure, Symptom
  Edges: DIAGNOSED_WITH(date), PRESCRIBED(date, dose), PRECEDED(delta_days),
         CORRELATED_WITH(r_value), CONTRAINDICATED_BY(source: RxNorm),
         RESULTED_IN(confidence)
  |
  v  ---- at query time ----
  v
[Hybrid Retrieval]
  KG traversal: causal/temporal/drug-safety Cypher queries
  Vector search: semantic similarity on finding embeddings (Qdrant)
  CBR: case-based reasoning -- ANN search over 847 anonymized timelines
  Merge into evidence pool with deduplication
  |
  v
[Evidence Ranker]
  Confidence tiers: HIGH (>=0.90), MEDIUM (0.70-0.90), LOW (<0.70)
  Source weighting: specialist model > KG > vector search
  Recency decay: older findings weighted down
  |
  v
[Constrained Generation -- Claude]
  Only uses evidence pool. Never draws on training data.
  Every claim must link to a source finding.
  |
  v
[Faithfulness Checker]
  Every output sentence cosine-matched to source evidence.
  Ungrounded sentences removed. Confidence tier shown.
  |
  v
[Output Formatter]
  EVIDENCE SUMMARY with HIGH/MEDIUM/LOW tiers
  Specialist consult flags (nephrology, cardiology, etc.)
  "This is a decision support tool. Clinical judgment required."
  |
  v
[Append-only Audit Log]
  SHA256 hash chain -- tamper-evident
  Stores: doctor_id, patient_id, query, retrieved_ids, model_version, output_hash
  Required for FDA audit trail and HIPAA compliance
```

---

## Temporal KG -- The Core Innovation

Standard RAG cannot answer:
- "Was the kidney decline before or after metformin was introduced?"
- "Which drug was added closest to the creatinine spike?"
- "Has this patient had adverse reactions to ACE inhibitors before?"

The KG can:

```cypher
MATCH (d:Drug {name: 'metformin'})-[:PRESCRIBED]->(p:Patient {id: $pid})
WITH p, d
MATCH (p)-[:HAS_LAB]->(lv:LabValue {name: 'eGFR'})
RETURN lv.value, lv.date ORDER BY lv.date DESC LIMIT 5
```

Combined with RxNorm contraindication rules, this produces:
"Metformin not currently contraindicated (eGFR 45 > 30), but eGFR has declined 12 points over 3 months. Monitor closely. [RxNorm:861004, Apollo Lab 2024-01-15]"

---

## PII Pipeline Details

```
1. Presidio NER scan: identifies PERSON, DATE, ID, ADDRESS, PHONE, EMAIL
2. Date shifting: each patient gets a secret random offset (e.g. +47 days)
   all dates shifted by same offset -> temporal gaps preserved, real dates gone
3. Name replacement: [PATIENT], [DOCTOR_1], [DOCTOR_2] (role-based, not random)
4. ID anonymization: SHA256(real_id + patient_salt)[:12]
5. Integrity diff-check:
   - All medical terms still present (ICD codes, drug names, lab values)
   - No clinical values (numbers) altered
   - Non-PII character count within 2% of original
6. Original document deleted from all storage (overwrite then delete)
7. De-identified version proceeds to indexing
```

---

## Case-Based Reasoning

After de-identification, each patient timeline is encoded as a fixed-dimensional embedding and stored in Qdrant. At query time, ANN search finds similar past timelines.

"Of 847 similar patients (Stage 3 CKD + T2DM + Metformin): 73% responded to dose reduction, 18% required insulin switch."

This is statistical evidence from real anonymized cases, not LLM hallucination.

---

## Hallucination Prevention -- Four Layers

| Layer | Mechanism |
|---|---|
| 1 | Specialist models for objective data (lab values from deterministic parsers) |
| 2 | KG traversal for relational queries (RxNorm-sourced drug rules) |
| 3 | Constrained generation (hard system prompt, no external knowledge) |
| 4 | Faithfulness checker (every sentence traced to source, ungrounded removed) |

---

## Quick Start

```bash
docker compose up -d
make install
python -m example.seed_patient
python -m example.run_query "Is metformin safe given this patient's declining kidney function?"
open http://localhost:8085/docs
```

---

## Project Structure

```
src/medical_rag/
  models.py            -- MedicalFinding, PatientTimeline, EvidenceItem, MedicalRAGResponse
  pii/                 -- Presidio de-identification + date shifting + integrity check
  ingestion/           -- Modality router + specialist processors + timeline construction
  knowledge_graph/     -- Neo4j client, KG builder, temporal Cypher traversals, RxNorm rules
  retrieval/           -- Hybrid KG + vector + CBR search, evidence ranking
  cbr/                 -- Timeline encoder + case library ANN search
  generation/          -- Constrained generation, faithfulness check, output formatter
  audit/               -- Append-only hash-chained audit log
  storage/             -- Postgres registry + Qdrant vector store
  api/                 -- FastAPI: ingest, query, audit endpoints
```

---

## Tools

| Component | Tool |
|---|---|
| KG storage | Neo4j 5 + Cypher |
| PII detection | Microsoft Presidio |
| Vector store | Qdrant (findings + patient timelines) |
| Medical NLP | Anthropic Claude (entity extraction) |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 |
| Drug interactions | RxNorm rules (hardcoded subset) |
| Audit log | PostgreSQL append-only with SHA256 hash chain |
| Observability | Prometheus + Grafana |
