"""HIPAA PII de-identification using Microsoft Presidio.

Pipeline:
1. Presidio NER scan: detect PII spans
2. Date shifting: all dates shifted by patient-specific fixed offset
3. Name/ID replacement
4. Integrity diff-check: verify medical values intact
5. Return de-identified text; caller must delete original
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import structlog

from medical_rag.pii.date_shifter import shift_dates_in_text

log = structlog.get_logger(__name__)

_MEDICAL_VALUE_PATTERN = re.compile(
    r"\b\d+\.?\d*\s*(?:mg|mcg|mEq|mmol|mg/dL|g/dL|U/L|IU/L|mL|L|mmHg|bpm|%|ng/mL|pg/mL|pmol/L|nmol/L)\b",
    re.IGNORECASE,
)
_ICD_PATTERN = re.compile(r"\b[A-Z]\d{2}(?:\.\d{1,4})?\b")
_LOINC_PATTERN = re.compile(r"\b\d{3,5}-\d\b")


@dataclass
class DeidentifyResult:
    deidentified_text: str
    entities_found: int
    dates_shifted: int
    integrity_ok: bool
    integrity_warnings: list[str]


def _anonymize_id(real_id: str, salt: str) -> str:
    digest = hashlib.sha256((real_id + salt).encode()).hexdigest()
    return f"[ID:{digest[:12]}]"


def _extract_medical_values(text: str) -> set[str]:
    vals: set[str] = set()
    for m in _MEDICAL_VALUE_PATTERN.finditer(text):
        vals.add(m.group(0).strip().lower())
    for m in _ICD_PATTERN.finditer(text):
        vals.add(m.group(0))
    for m in _LOINC_PATTERN.finditer(text):
        vals.add(m.group(0))
    return vals


def deidentify(text: str, patient_id: str) -> DeidentifyResult:
    """De-identify text using Presidio + date shifting."""
    original_medical = _extract_medical_values(text)
    entities_found = 0
    warnings: list[str] = []

    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
        from presidio_anonymizer.entities import OperatorConfig

        analyzer = AnalyzerEngine()
        anonymizer = AnonymizerEngine()

        results = analyzer.analyze(text=text, language="en")
        entities_found = len(results)

        date_results = [r for r in results if r.entity_type == "DATE_TIME"]
        non_date_results = [r for r in results if r.entity_type != "DATE_TIME"]

        operators: dict[str, OperatorConfig] = {}
        for entity_type in {"PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "URL",
                            "LOCATION", "NRP", "MEDICAL_LICENSE", "US_SSN",
                            "US_PASSPORT", "US_ITIN", "CREDIT_CARD"}:
            operators[entity_type] = OperatorConfig("replace", {"new_value": f"[{entity_type}]"})

        if non_date_results:
            result = anonymizer.anonymize(
                text=text,
                analyzer_results=non_date_results,
                operators=operators,
            )
            text = result.text

        if date_results:
            text = shift_dates_in_text(text, patient_id)
            dates_shifted = len(date_results)
        else:
            text = shift_dates_in_text(text, patient_id)
            dates_shifted = 0

    except ImportError:
        log.warning("presidio_not_installed", msg="Falling back to regex-only de-identification")
        text = shift_dates_in_text(text, patient_id)
        text = re.sub(r"\b(?:Dr\.?|Mr\.?|Mrs\.?|Ms\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", "[PERSON]", text)
        text = re.sub(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", "[PERSON]", text)
        entities_found = 0
        dates_shifted = 0

    post_medical = _extract_medical_values(text)
    missing = original_medical - post_medical
    if missing:
        for m in missing:
            warnings.append(f"Medical value possibly altered: {m!r}")
        integrity_ok = len(missing) == 0
    else:
        integrity_ok = True

    orig_len = len(re.sub(r"\s+", " ", text))
    if orig_len > 0:
        ratio = abs(len(text) - orig_len) / orig_len
        if ratio > 0.02:
            warnings.append(f"Character count deviation {ratio:.1%} exceeds 2%")

    log.info(
        "pii_deidentified",
        patient_id=patient_id,
        entities=entities_found,
        dates_shifted=dates_shifted,
        integrity_ok=integrity_ok,
        warnings=warnings,
    )

    return DeidentifyResult(
        deidentified_text=text,
        entities_found=entities_found,
        dates_shifted=dates_shifted,
        integrity_ok=integrity_ok,
        integrity_warnings=warnings,
    )
