"""Hybrid retrieval: KG traversal + Qdrant vector search, merged and deduplicated."""

from __future__ import annotations

import structlog

from medical_rag.config import get_settings
from medical_rag.knowledge_graph.traversal import get_kg_summary_for_query, get_active_drugs, get_lab_trend
from medical_rag.knowledge_graph.rxnorm import check_interactions
from medical_rag.models import ConfidenceTier, DrugInteractionWarning, EvidenceItem
from medical_rag.storage.qdrant_store import search_findings

log = structlog.get_logger(__name__)


async def hybrid_retrieve(
    patient_id: str,
    query: str,
    top_k: int = 10,
) -> tuple[list[EvidenceItem], list[DrugInteractionWarning]]:
    """Merge KG + vector evidence, dedup by content hash."""
    cfg = get_settings()

    vector_evidence = await search_findings(query, patient_id, top_k=top_k)

    kg_text = await get_kg_summary_for_query(patient_id, query)
    kg_evidence: list[EvidenceItem] = []
    if kg_text and kg_text != "No KG data available for this patient.":
        kg_evidence.append(EvidenceItem(
            source_type="kg_traversal",
            source_id=f"kg:{patient_id}",
            content=kg_text,
            confidence=0.92,
            tier=ConfidenceTier.HIGH,
        ))

    drugs_raw = await get_active_drugs(patient_id)
    active_drugs = [d["drug_name"] for d in drugs_raw if d.get("drug_name")]

    egfr_trend = await get_lab_trend(patient_id, "eGFR")
    lab_values: dict[str, float] = {}
    if egfr_trend:
        lab_values["egfr"] = float(egfr_trend[-1]["value"])

    creatinine_trend = await get_lab_trend(patient_id, "creatinine")
    if creatinine_trend:
        lab_values["creatinine"] = float(creatinine_trend[-1]["value"])

    drug_warnings = check_interactions(active_drugs, lab_values)

    if drug_warnings:
        warning_text = "\n".join(
            f"DRUG INTERACTION [{w.severity.value.upper()}]: {w.drug_a} + {w.drug_b}. "
            f"{w.recommendation} [{w.rxnorm_source}]"
            for w in drug_warnings
        )
        kg_evidence.append(EvidenceItem(
            source_type="rxnorm_rules",
            source_id="rxnorm",
            content=warning_text,
            confidence=0.98,
            tier=ConfidenceTier.HIGH,
        ))

    all_evidence = kg_evidence + vector_evidence

    seen: set[str] = set()
    deduped: list[EvidenceItem] = []
    for ev in all_evidence:
        key = ev.content[:100]
        if key not in seen:
            seen.add(key)
            deduped.append(ev)

    deduped.sort(key=lambda e: e.confidence, reverse=True)

    log.info(
        "hybrid_retrieve_done",
        patient_id=patient_id,
        vector_count=len(vector_evidence),
        kg_count=len(kg_evidence),
        drug_warnings=len(drug_warnings),
        total_deduped=len(deduped),
    )
    return deduped, drug_warnings
