"""ECG processor stub -- cardiology model interface.

In production this would call a PTB-XL trained classifier.
Returns structured MedicalFinding with standard ECG findings.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog

from medical_rag.models import MedicalEntity, MedicalFinding, ModalityType, Severity

log = structlog.get_logger(__name__)

_ECG_CRITICAL_FINDINGS = {
    "stemi", "vfib", "vtach", "complete_heart_block", "third_degree_av_block",
    "brugada_pattern", "long_qt_syndrome",
}


def process_ecg(
    data: dict[str, Any], patient_id: str, source_doc: str, finding_date: date
) -> MedicalFinding:
    rhythm = data.get("rhythm", "normal_sinus")
    heart_rate = data.get("heart_rate_bpm", 72)
    pr_interval = data.get("pr_interval_ms")
    qrs_duration = data.get("qrs_duration_ms")
    qt_corrected = data.get("qt_corrected_ms")
    findings_raw: list[str] = data.get("findings", [])
    interpretation = data.get("interpretation", "")

    entities = [
        MedicalEntity(entity_type="FINDING", value=f, confidence=0.82)
        for f in findings_raw
    ]

    if rhythm != "normal_sinus":
        entities.append(MedicalEntity(entity_type="FINDING", value=f"rhythm: {rhythm}", confidence=0.90))

    is_critical = any(f.lower().replace(" ", "_") in _ECG_CRITICAL_FINDINGS for f in findings_raw)
    is_abnormal = (
        is_critical
        or (heart_rate < 50 or heart_rate > 100)
        or (qt_corrected is not None and qt_corrected > 450)
        or len(findings_raw) > 0
    )

    severity = Severity.CRITICAL if is_critical else (Severity.HIGH if is_abnormal else Severity.NORMAL)

    log.info(
        "ecg_processor_done",
        patient_id=patient_id,
        rhythm=rhythm,
        hr=heart_rate,
        is_abnormal=is_abnormal,
    )

    return MedicalFinding(
        patient_id=patient_id,
        modality=ModalityType.ECG,
        finding_date=finding_date,
        source_document=source_doc,
        entities=entities,
        raw_text=interpretation or f"Rhythm: {rhythm}, HR: {heart_rate} bpm, Findings: {', '.join(findings_raw)}",
        structured_data={
            "rhythm": rhythm,
            "heart_rate_bpm": heart_rate,
            "pr_interval_ms": pr_interval,
            "qrs_duration_ms": qrs_duration,
            "qt_corrected_ms": qt_corrected,
        },
        confidence=0.88,
        is_abnormal=is_abnormal,
        severity=severity,
        specialist_flags=["cardiology"] if is_abnormal else [],
    )
