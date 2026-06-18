"""Encode a patient timeline into a fixed-dimensional embedding for CBR."""

from __future__ import annotations

from medical_rag.models import PatientTimeline


def encode_timeline(timeline: PatientTimeline) -> str:
    """Produce a canonical text summary of the timeline for embedding."""
    parts: list[str] = []

    conditions: list[str] = []
    drugs: list[str] = []
    abnormal_labs: list[str] = []

    for finding in timeline.sorted_findings():
        for entity in finding.entities:
            if entity.entity_type.upper() == "CONDITION":
                conditions.append(entity.normalized or entity.value)
            elif entity.entity_type.upper() == "DRUG":
                drugs.append(entity.normalized or entity.value)

        for lr in finding.lab_results:
            if lr.is_abnormal:
                abnormal_labs.append(f"{lr.test_name}:{lr.value}{lr.unit}")

    if conditions:
        parts.append("Conditions: " + ", ".join(sorted(set(conditions))))
    if drugs:
        parts.append("Medications: " + ", ".join(sorted(set(drugs))))
    if abnormal_labs:
        parts.append("Abnormal labs: " + "; ".join(abnormal_labs[:10]))

    return " | ".join(parts) if parts else "No structured findings"
