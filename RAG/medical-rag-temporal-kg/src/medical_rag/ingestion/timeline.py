"""Build and update PatientTimeline from MedicalFinding objects."""

from __future__ import annotations

from medical_rag.models import MedicalFinding, PatientTimeline


def build_timeline(patient_id: str, findings: list[MedicalFinding]) -> PatientTimeline:
    return PatientTimeline(
        patient_id=patient_id,
        findings=sorted(findings, key=lambda f: f.finding_date),
    )


def merge_into_timeline(
    timeline: PatientTimeline, new_findings: list[MedicalFinding]
) -> PatientTimeline:
    existing_ids = {f.finding_id for f in timeline.findings}
    merged = list(timeline.findings)
    for f in new_findings:
        if f.finding_id not in existing_ids:
            merged.append(f)
    return PatientTimeline(
        patient_id=timeline.patient_id,
        findings=sorted(merged, key=lambda f: f.finding_date),
        date_shift_days=timeline.date_shift_days,
    )
