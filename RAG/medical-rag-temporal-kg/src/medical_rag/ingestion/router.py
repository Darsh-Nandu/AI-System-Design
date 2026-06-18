"""Modality router -- dispatches raw documents to specialist processors."""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog

from medical_rag.models import ModalityType, MedicalFinding
from medical_rag.pii.deidentifier import deidentify
from medical_rag.ingestion.processors.text_processor import process_text
from medical_rag.ingestion.processors.lab_processor import process_lab
from medical_rag.ingestion.processors.imaging_processor import process_imaging
from medical_rag.ingestion.processors.ecg_processor import process_ecg

log = structlog.get_logger(__name__)


def _detect_modality(doc: dict[str, Any]) -> ModalityType:
    explicit = doc.get("modality", "").lower()
    if explicit in ModalityType._value2member_map_:
        return ModalityType(explicit)

    content = str(doc.get("content", "") or doc.get("report", "") or doc.get("text", "")).lower()

    if any(k in content for k in ["rhythm", "sinus", "bpm", "ecg", "ekg", "qt interval"]):
        return ModalityType.ECG
    if any(k in content for k in ["mri", "ct scan", "x-ray", "ultrasound", "imaging", "radiology"]):
        return ModalityType.IMAGING
    if any(k in doc for k in ["labs", "lab_results"]) or content.startswith("lab panel"):
        return ModalityType.LAB
    return ModalityType.TEXT


async def route_document(
    doc: dict[str, Any], patient_id: str, source_id: str
) -> MedicalFinding:
    finding_date_raw = doc.get("date", doc.get("finding_date", str(date.today())))
    if isinstance(finding_date_raw, date):
        finding_date = finding_date_raw
    else:
        finding_date = date.fromisoformat(str(finding_date_raw))

    modality = _detect_modality(doc)

    text_content = str(
        doc.get("content") or doc.get("report") or doc.get("text") or doc.get("raw_text", "")
    )
    if text_content:
        result = deidentify(text_content, patient_id)
        if not result.integrity_ok:
            log.warning(
                "integrity_check_failed",
                patient_id=patient_id,
                warnings=result.integrity_warnings,
            )
        if modality == ModalityType.TEXT:
            doc = {**doc, "content": result.deidentified_text}
        else:
            doc = {**doc, "raw_text": result.deidentified_text}

    log.info("routing_document", patient_id=patient_id, modality=modality.value, source=source_id)

    if modality == ModalityType.TEXT:
        return await process_text(
            doc.get("content", ""), patient_id, source_id, finding_date
        )
    elif modality == ModalityType.LAB:
        return process_lab(doc, patient_id, source_id, finding_date)
    elif modality == ModalityType.IMAGING:
        return process_imaging(doc, patient_id, source_id, finding_date)
    elif modality == ModalityType.ECG:
        return process_ecg(doc, patient_id, source_id, finding_date)
    else:
        return await process_text(
            doc.get("content", ""), patient_id, source_id, finding_date
        )
