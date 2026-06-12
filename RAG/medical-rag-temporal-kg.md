# Medical RAG with Temporal Knowledge Graph

**Domain:** Medical second-opinion systems, clinical decision support  
**Interview question:** *"Design a RAG system for a medical AI that reasons over a patient's full history across PDFs, lab results, and imaging. It must never hallucinate, must cite sources, and must be HIPAA compliant."*  
**Industry reference:** Google Med-PaLM 2, Microsoft BioGPT, Epic Systems

---

## The Core Problem

Medical AI is harder than legal RAG for four reasons:

1. Patient data spans multiple modalities - text reports, lab numbers, MRI images, ECG signals. No single model handles all of them well.
2. Reasoning requires *temporal* connections - "kidney function declined 3 months after drug X was introduced" is causal, not just semantic.
3. Hallucination is life-threatening, not just legally inconvenient.
4. Patient data is maximally sensitive - HIPAA violations carry criminal penalties.

This design addresses all four.

---

## Architecture Overview

```
Doctor uploads patient documents
  │
  ▼
[Ingestion Pipeline]
  ├── PII De-identification (Presidio)
  ├── Integrity diff-check (original vs de-identified)
  ├── Original document deletion
  └── Modality routing:
        ├── Text reports → NLP pipeline
        ├── Lab results → structured parser
        ├── MRI/CT scans → radiology ML model (Med-SAM)
        ├── ECG → cardiology model
        └── Blood panels → lab interpretation model
  │
  ▼
[Timeline Construction]
  │  each event stamped: { date, type, source, result, confidence }
  │  specialist model outputs converted to structured findings
  ▼
[Temporal Knowledge Graph Builder]
  │  nodes: medical events, conditions, drugs, procedures
  │  edges: temporal (before/after), causal (caused/triggered),
  │         correlational (associated with)
  ▼
[KG stored + Document Cards indexed in vector store]
  │
  ▼  ── at query time ──
  │
[Query understanding]
  │  parse constraints: drug names, timeframes, organ systems
  ▼
[KG traversal + Vector search]
  │  KG answers causal/temporal queries
  │  vector search answers semantic queries
  │  results merged into evidence pool
  ▼
[Evidence ranker + confidence scorer]
  │  each piece of evidence gets: source, date, confidence tier
  ▼
[Constrained generation with citation grounding]
  │  model only uses evidence pool
  │  every claim linked to source chunk + page
  ▼
[Faithfulness checker]
  ▼
Answer → Doctor (with citations, confidence tiers, "consult specialist" flags)
```

---

## Specialist Model Routing

Different medical data types require specialist models - a general LLM cannot reliably interpret MRI scans or ECG waveforms.

| Input type | Specialist model | Output |
|---|---|---|
| MRI / CT scan | Med-SAM, BioViL-T | Structured finding: region, anomaly type, severity |
| Blood panel | Lab interpretation model | Each value: normal/abnormal/critical + delta from last test |
| ECG | Cardiology model | Rhythm classification, interval measurements |
| Pathology slide | PathAI | Cell type distribution, abnormality flags |
| Text report | NLP pipeline (BioBERT) | Entity extraction: conditions, drugs, procedures, dates |

All specialist outputs are converted to a **structured finding object** before entering the timeline:

```
Finding {
  date: "2024-01-15"
  type: "lab_result"
  source: "Apollo Hospital, Mumbai"
  source_id: "IN:MH:MUM:APOLLO:LAB:20240115:CBC"
  finding: "eGFR: 45 mL/min/1.73m²"
  interpretation: "Stage 3 CKD - moderate kidney function reduction"
  confidence: 0.97        ← from specialist model
  reference_range: "normal: >60"
  delta: "-12 from 3 months ago"
}
```

---

## Temporal Knowledge Graph

The KG is the core innovation that separates this from standard RAG.

**Why a KG and not just a vector store?**

Vector search finds semantically similar content. It cannot answer:
- "Was the kidney decline before or after metformin was introduced?"
- "Which drug was added closest to when the creatinine spike occurred?"
- "Has this patient had adverse reactions to ACE inhibitors before?"

These require *temporal reasoning over relationships* - exactly what a KG provides.

**KG structure:**

```
Nodes:
  - Patient (anonymized)
  - Condition (e.g., Type 2 Diabetes, CKD Stage 3)
  - Drug (e.g., Metformin 500mg)
  - Procedure (e.g., Kidney biopsy)
  - LabValue (e.g., eGFR 45)
  - Symptom

Edges:
  - DIAGNOSED_WITH (date)
  - PRESCRIBED (date, dose)
  - UNDERWENT (date)
  - RESULTED_IN (confidence, evidence_source)
  - PRECEDED (time_delta)
  - CORRELATED_WITH (r_value)
  - CONTRAINDICATED_BY (source: RxNorm)
```

**Example traversal for query** *"Is metformin safe given this patient's kidney function?"*:

1. Find node: Drug(Metformin)
2. Traverse CONTRAINDICATED_BY → finds RxNorm rule: "contraindicated if eGFR < 30"
3. Find most recent LabValue(eGFR) → 45 mL/min
4. Temporal check: is this value current? Last updated 2 weeks ago → yes
5. Evaluate: eGFR 45 > 30 → not contraindicated, but find edge CORRELATED_WITH → eGFR declining trend
6. Output: "Metformin not currently contraindicated (eGFR 45), however eGFR has declined 12 points in 3 months. Monitor closely. Source: RxNorm ID 861004, patient lab 2024-01-15."

This answer is impossible from a flat vector store.

---

## PII De-identification Pipeline

Medical documents contain maximally sensitive PII: names, addresses, ID numbers, dates of birth, insurance IDs.

**Pipeline:**

```
1. Raw document ingested
2. Presidio NER scan → identifies all PII spans
3. Replacement:
     - Names → [PATIENT], [DOCTOR_1], [DOCTOR_2]
     - Dates → shifted by fixed random offset (preserves temporal relationships)
     - ID numbers → anonymized hash
     - Addresses → city-level only
4. Integrity diff-check:
     - Compare original vs de-identified
     - Verify: all medical terms preserved, no clinical values altered
     - Check: character count of non-PII sections matches within 2%
5. Original document deleted from all storage
6. De-identified document proceeds to indexing
```

**Why the diff-check matters:**

Aggressive PII removal sometimes strips medical context. Example: "Patient John Smith's eGFR" → if the model removes "John Smith's" it might accidentally remove "eGFR" nearby. The diff-check catches this before the document enters the knowledge base.

**Date shifting:**

Dates are shifted by a fixed random offset per patient (e.g., +47 days for all dates). This preserves temporal relationships (drug introduced 3 months before kidney decline) while making real dates unrecoverable.

---

## Case-Based Reasoning - Timeline Reuse

After de-identification, anonymized patient timelines are stored in a **timeline library**.

When a new patient is ingested:
1. Embed the patient's condition profile and timeline shape
2. ANN search over timeline library for similar cases
3. Return top-K similar timelines with outcomes

This enables reasoning like:
*"Of 847 similar patients with Stage 3 CKD + Type 2 Diabetes + Metformin, 73% responded well to dose reduction, 18% required switch to insulin."*

This is **case-based reasoning (CBR)** - statistical evidence from real anonymized cases, not LLM hallucination.

---

## Hallucination Prevention - Four Layers

**Layer 1 - Specialist models for objective data:** Lab values and imaging findings come from deterministic models, not LLM interpretation. Numbers don't hallucinate.

**Layer 2 - KG traversal for relational queries:** Drug interactions answered by traversing RxNorm-sourced KG edges, not LLM knowledge.

**Layer 3 - Constrained generation:** Hard system prompt: "You are a medical decision support tool. Only state information present in the provided evidence pool. If insufficient evidence exists, say so explicitly. Never infer beyond what is stated."

**Layer 4 - Faithfulness checker:** Every sentence in output traced to a source chunk. Ungrounded sentences removed. Confidence tier shown to doctor.

---

## Output Design - Augment, Not Replace

The system never tells the doctor they are wrong. It presents evidence.

```
Query: "Is this drug combination safe?"

Output format:
─────────────────────────────────────
EVIDENCE SUMMARY
─────────────────────────────────────
[HIGH CONFIDENCE] Metformin + Lisinopril: No known interaction
  Source: RxNorm interaction DB, last updated 2024-01-01

[MEDIUM CONFIDENCE] Patient eGFR trending down: 57 → 45 over 6 months
  Source: Apollo Lab reports, 2023-07-15 and 2024-01-15
  Note: Metformin dose reduction recommended if eGFR < 45

[FLAG] 3 similar patient timelines showed eGFR drop below 30 within
  4 months of this trajectory. Nephrology consult may be warranted.
  Source: Anonymized case library (n=847)
─────────────────────────────────────
⚠ This is a decision support tool. Clinical judgment required.
─────────────────────────────────────
```

---

## Compliance & Audit

Every query generates an immutable audit log entry:

```
AuditEntry {
  timestamp: "2024-01-20T14:32:11Z"
  doctor_id: "hashed"
  patient_id: "anonymized"
  query: "Is this drug combination safe..."
  retrieved_chunks: ["chunk_id_1", "chunk_id_2", ...]
  model_version: "med-rag-v1.2.0"        ← frozen, never changes
  output_hash: "sha256:abc123..."
  faithfulness_score: 0.97
}
```

Stored in append-only log (AWS QLDB or Kafka with infinite retention). Cannot be edited or deleted. Required for FDA audit trail and HIPAA compliance.

**Model version locking:** The model version that produced a recommendation is frozen in the audit entry. If a doctor made a decision based on v1.2, and the system is now on v2.0, v1.2 must still be queryable for audit review.

---

## Tradeoffs

| Decision | Benefit | Cost |
|---|---|---|
| Specialist models per modality | High accuracy on imaging/labs | Complex routing, multiple model deployments |
| Temporal KG | Causal reasoning, temporal queries | High ingestion complexity, KG maintenance |
| Date shifting for PII | Preserves temporal relationships | Requires consistent offset management per patient |
| CBR timeline library | Evidence from real cases | Requires large anonymized dataset to be useful |
| Append-only audit log | Compliance, full auditability | Storage grows indefinitely |

---

## Tools Referenced

| Component | Tool |
|---|---|
| PII de-identification | Microsoft Presidio |
| Medical NLP | BioBERT, Med-BERT |
| Radiology model | Med-SAM, BioViL-T |
| Drug interaction DB | RxNorm, SNOMED-CT |
| Vector store | Qdrant |
| KG storage | Neo4j |
| Audit log | AWS QLDB |
| Faithfulness check | RAGAS |