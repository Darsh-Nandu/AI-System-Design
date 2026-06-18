"""Structured lab panel processor.

Parses structured lab data (dict or text) into LabResult objects with
reference ranges, abnormality flags, and severity classification.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import structlog

from medical_rag.models import LabResult, MedicalFinding, ModalityType, Severity

log = structlog.get_logger(__name__)

_REFERENCE_RANGES: dict[str, tuple[float, float, str]] = {
    "egfr": (60.0, 120.0, "mL/min/1.73m2"),
    "creatinine": (0.6, 1.2, "mg/dL"),
    "bun": (7.0, 25.0, "mg/dL"),
    "hemoglobin": (12.0, 17.5, "g/dL"),
    "hba1c": (4.0, 5.7, "%"),
    "glucose": (70.0, 100.0, "mg/dL"),
    "sodium": (136.0, 145.0, "mEq/L"),
    "potassium": (3.5, 5.0, "mEq/L"),
    "alt": (7.0, 56.0, "U/L"),
    "ast": (10.0, 40.0, "U/L"),
    "total_cholesterol": (0.0, 200.0, "mg/dL"),
    "ldl": (0.0, 100.0, "mg/dL"),
    "hdl": (40.0, 99999.0, "mg/dL"),
    "triglycerides": (0.0, 150.0, "mg/dL"),
    "tsh": (0.4, 4.0, "mIU/L"),
    "wbc": (4.5, 11.0, "K/uL"),
    "platelets": (150.0, 400.0, "K/uL"),
}

_LOINC_CODES: dict[str, str] = {
    "egfr": "48642-3",
    "creatinine": "2160-0",
    "bun": "3094-0",
    "hemoglobin": "718-7",
    "hba1c": "4548-4",
    "glucose": "2339-0",
    "sodium": "2951-2",
    "potassium": "2823-3",
    "alt": "1742-6",
    "ast": "1920-8",
    "total_cholesterol": "2093-3",
    "ldl": "2089-1",
    "hdl": "2085-9",
    "triglycerides": "2571-8",
    "tsh": "3016-3",
    "wbc": "6690-2",
    "platelets": "777-3",
}


def _classify_severity(name: str, value: float, lo: float, hi: float) -> Severity:
    if lo <= value <= hi:
        return Severity.NORMAL
    deviation = max((lo - value) / lo if lo > 0 else 0, (value - hi) / hi if hi > 0 else 0)
    if deviation > 0.5:
        return Severity.CRITICAL
    if deviation > 0.3:
        return Severity.HIGH
    if deviation > 0.1:
        return Severity.MODERATE
    return Severity.LOW


def _parse_lab_text(text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    pattern = re.compile(
        r"([A-Za-z][A-Za-z0-9\s_/]+?):\s*([\d.]+)\s*([A-Za-z/%]+(?:/[A-Za-z0-9]+)?)?",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        name = m.group(1).strip().lower().replace(" ", "_")
        try:
            value = float(m.group(2))
        except ValueError:
            continue
        unit = m.group(3) or ""
        results.append({"test_name": name, "value": value, "unit": unit})
    return results


def process_lab(
    data: dict[str, Any], patient_id: str, source_doc: str, finding_date: date
) -> MedicalFinding:
    raw_text = data.get("raw_text", "")
    lab_entries: list[dict[str, Any]] = data.get("labs", [])

    if not lab_entries and raw_text:
        lab_entries = _parse_lab_text(raw_text)

    lab_results: list[LabResult] = []
    any_abnormal = False
    worst_severity = Severity.NORMAL

    sev_rank = {Severity.CRITICAL: 4, Severity.HIGH: 3, Severity.MODERATE: 2, Severity.LOW: 1, Severity.NORMAL: 0}

    for entry in lab_entries:
        name_key = entry.get("test_name", "").lower().replace(" ", "_")
        value = float(entry.get("value", 0))
        unit = entry.get("unit", "")
        prev_value: float | None = entry.get("previous_value")

        ref_lo, ref_hi, ref_unit = _REFERENCE_RANGES.get(name_key, (None, None, unit))  # type: ignore[assignment]
        loinc = _LOINC_CODES.get(name_key)

        is_abnormal = False
        severity = Severity.NORMAL
        if ref_lo is not None and ref_hi is not None:
            is_abnormal = not (ref_lo <= value <= ref_hi)
            severity = _classify_severity(name_key, value, ref_lo, ref_hi)

        delta = (value - prev_value) if prev_value is not None else None

        if is_abnormal:
            any_abnormal = True
        if sev_rank[severity] > sev_rank[worst_severity]:
            worst_severity = severity

        lab_results.append(LabResult(
            test_name=entry.get("test_name", name_key),
            loinc_code=loinc,
            value=value,
            unit=unit or (ref_unit if ref_unit else ""),
            reference_low=ref_lo,
            reference_high=ref_hi,
            is_abnormal=is_abnormal,
            delta_from_previous=delta,
            severity=severity,
        ))

    specialist_flags: list[str] = []
    for lr in lab_results:
        k = lr.test_name.lower().replace(" ", "_")
        if k in {"egfr", "creatinine", "bun"} and lr.is_abnormal:
            specialist_flags.append("nephrology")
        if k in {"total_cholesterol", "ldl"} and lr.is_abnormal:
            specialist_flags.append("cardiology")
        if k == "hba1c" and lr.is_abnormal:
            specialist_flags.append("endocrinology")

    log.info(
        "lab_processor_done",
        patient_id=patient_id,
        tests=len(lab_results),
        abnormal_count=sum(1 for lr in lab_results if lr.is_abnormal),
    )

    return MedicalFinding(
        patient_id=patient_id,
        modality=ModalityType.LAB,
        finding_date=finding_date,
        source_document=source_doc,
        lab_results=lab_results,
        raw_text=raw_text,
        structured_data=data,
        confidence=0.98,
        is_abnormal=any_abnormal,
        severity=worst_severity,
        specialist_flags=list(set(specialist_flags)),
    )
