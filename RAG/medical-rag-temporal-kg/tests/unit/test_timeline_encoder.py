"""Tests for patient timeline encoding for CBR."""

from __future__ import annotations

from datetime import date

import pytest

from medical_rag.cbr.timeline_encoder import encode_timeline
from medical_rag.models import MedicalEntity, MedicalFinding, ModalityType, PatientTimeline


def _make_finding(patient_id: str, entities: list[dict]) -> MedicalFinding:
    return MedicalFinding(
        patient_id=patient_id,
        modality=ModalityType.TEXT,
        finding_date=date(2024, 1, 1),
        source_document="test.pdf",
        entities=[MedicalEntity(**e) for e in entities],
    )


def test_encode_includes_conditions():
    finding = _make_finding("p1", [
        {"entity_type": "CONDITION", "value": "Type 2 Diabetes", "confidence": 0.95},
    ])
    timeline = PatientTimeline(patient_id="p1", findings=[finding])
    encoded = encode_timeline(timeline)
    assert "Conditions" in encoded
    assert "Type 2 Diabetes" in encoded


def test_encode_includes_drugs():
    finding = _make_finding("p1", [
        {"entity_type": "DRUG", "value": "metformin", "confidence": 0.98},
    ])
    timeline = PatientTimeline(patient_id="p1", findings=[finding])
    encoded = encode_timeline(timeline)
    assert "metformin" in encoded.lower()


def test_empty_timeline_returns_fallback():
    timeline = PatientTimeline(patient_id="p_empty", findings=[])
    encoded = encode_timeline(timeline)
    assert "No structured findings" in encoded


def test_deduplicates_repeated_entities():
    findings = [
        _make_finding("p1", [{"entity_type": "CONDITION", "value": "CKD", "confidence": 0.9}]),
        _make_finding("p1", [{"entity_type": "CONDITION", "value": "CKD", "confidence": 0.9}]),
    ]
    timeline = PatientTimeline(patient_id="p1", findings=findings)
    encoded = encode_timeline(timeline)
    assert encoded.count("CKD") == 1
