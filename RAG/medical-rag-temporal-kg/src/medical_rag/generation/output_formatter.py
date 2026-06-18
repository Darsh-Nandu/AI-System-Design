"""Format the final MedicalRAGResponse with tiered evidence and specialist flags."""

from __future__ import annotations

from medical_rag.models import (
    CBRMatch,
    ConfidenceTier,
    DrugInteractionWarning,
    EvidenceItem,
    MedicalRAGResponse,
)


def format_response(
    patient_id: str,
    query: str,
    evidence: list[EvidenceItem],
    generated_answer: str,
    ungrounded: list[str],
    faithfulness_score: float,
    drug_warnings: list[DrugInteractionWarning],
    cbr_matches: list[CBRMatch],
) -> MedicalRAGResponse:
    high = [ev for ev in evidence if ev.tier == ConfidenceTier.HIGH]
    medium = [ev for ev in evidence if ev.tier == ConfidenceTier.MEDIUM]
    low = [ev for ev in evidence if ev.tier == ConfidenceTier.LOW]

    all_flags: set[str] = set()
    for ev in evidence:
        all_flags.update(ev.specialist_flags)

    if drug_warnings:
        critical_warn = any(w.severity.value in {"critical", "high"} for w in drug_warnings)
        if critical_warn:
            all_flags.add("clinical_pharmacology")

    specialist_consults = sorted(all_flags)

    return MedicalRAGResponse(
        patient_id=patient_id,
        query=query,
        high_confidence_evidence=high,
        medium_confidence_evidence=medium,
        low_confidence_evidence=low,
        cbr_matches=cbr_matches,
        drug_warnings=drug_warnings,
        generated_answer=generated_answer,
        specialist_consults=specialist_consults,
        ungrounded_sentences=ungrounded,
        faithfulness_score=faithfulness_score,
    )
