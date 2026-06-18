"""Imaging processor stub -- Med-SAM compatible interface.

In production this would call a Med-SAM or similar model inference endpoint.
Structured output is the same MedicalFinding regardless of backend.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog

from medical_rag.models import MedicalEntity, MedicalFinding, ModalityType, Severity

log = structlog.get_logger(__name__)


def process_imaging(
    data: dict[str, Any], patient_id: str, source_doc: str, finding_date: date
) -> MedicalFinding:
    modality_tag = data.get("modality", "MRI").upper()
    body_part = data.get("body_part", "")
    report_text = data.get("report", "")
    findings_raw: list[str] = data.get("findings", [])

    entities = [
        MedicalEntity(entity_type="FINDING", value=f, confidence=0.80)
        for f in findings_raw
    ]

    is_abnormal = data.get("is_abnormal", len(findings_raw) > 0)
    severity_raw = data.get("severity", "normal").lower()
    try:
        severity = Severity(severity_raw)
    except ValueError:
        severity = Severity.NORMAL

    specialist_flags: list[str] = []
    if "brain" in body_part.lower() or "head" in body_part.lower():
        specialist_flags.append("neurology")
    if "heart" in body_part.lower() or "cardiac" in body_part.lower():
        specialist_flags.append("cardiology")
    if "lung" in body_part.lower() or "chest" in body_part.lower():
        specialist_flags.append("pulmonology")

    log.info(
        "imaging_processor_done",
        patient_id=patient_id,
        modality=modality_tag,
        body_part=body_part,
        findings=len(findings_raw),
    )

    return MedicalFinding(
        patient_id=patient_id,
        modality=ModalityType.IMAGING,
        finding_date=finding_date,
        source_document=source_doc,
        entities=entities,
        raw_text=report_text or "; ".join(findings_raw),
        structured_data={"modality": modality_tag, "body_part": body_part, **data},
        confidence=0.75,
        is_abnormal=is_abnormal,
        severity=severity,
        specialist_flags=specialist_flags,
    )
