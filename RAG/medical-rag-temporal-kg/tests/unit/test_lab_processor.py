"""Tests for the structured lab panel processor."""

from __future__ import annotations

from datetime import date

import pytest

from medical_rag.ingestion.processors.lab_processor import process_lab
from medical_rag.models import ModalityType, Severity


def _make_lab(labs: list[dict], raw_text: str = "") -> dict:
    return {"labs": labs, "raw_text": raw_text}


def test_normal_lab_not_abnormal():
    doc = _make_lab([{"test_name": "eGFR", "value": 85, "unit": "mL/min/1.73m2"}])
    finding = process_lab(doc, "p1", "lab_panel.pdf", date(2024, 1, 1))
    assert finding.modality == ModalityType.LAB
    assert not finding.is_abnormal
    assert finding.lab_results[0].severity == Severity.NORMAL


def test_abnormal_egfr_flagged():
    doc = _make_lab([{"test_name": "eGFR", "value": 25, "unit": "mL/min/1.73m2"}])
    finding = process_lab(doc, "p1", "lab.pdf", date(2024, 1, 1))
    assert finding.is_abnormal
    assert finding.lab_results[0].is_abnormal
    assert finding.lab_results[0].severity in (Severity.CRITICAL, Severity.HIGH)
    assert "nephrology" in finding.specialist_flags


def test_delta_computed():
    doc = _make_lab([{
        "test_name": "creatinine",
        "value": 1.8,
        "unit": "mg/dL",
        "previous_value": 1.2,
    }])
    finding = process_lab(doc, "p1", "lab.pdf", date(2024, 1, 1))
    assert finding.lab_results[0].delta_from_previous == pytest.approx(0.6, abs=0.01)


def test_loinc_code_assigned():
    doc = _make_lab([{"test_name": "eGFR", "value": 80, "unit": "mL/min/1.73m2"}])
    finding = process_lab(doc, "p1", "lab.pdf", date(2024, 1, 1))
    assert finding.lab_results[0].loinc_code == "48642-3"


def test_high_confidence_for_lab():
    doc = _make_lab([{"test_name": "hemoglobin", "value": 14.5, "unit": "g/dL"}])
    finding = process_lab(doc, "p1", "lab.pdf", date(2024, 1, 1))
    assert finding.confidence >= 0.95
