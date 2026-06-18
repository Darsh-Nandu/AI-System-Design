"""Tests for deterministic date shifting."""

from __future__ import annotations

from datetime import date

import pytest

from medical_rag.pii.date_shifter import _patient_offset, shift_date, shift_dates_in_text


def test_offset_is_deterministic():
    pid = "patient-abc-123"
    o1 = _patient_offset(pid)
    o2 = _patient_offset(pid)
    assert o1 == o2


def test_different_patients_different_offsets():
    o1 = _patient_offset("patient-A")
    o2 = _patient_offset("patient-B")
    assert o1 != o2


def test_offset_within_bounds():
    from medical_rag.config import get_settings
    max_days = get_settings().max_date_shift_days
    for pid in ["p1", "p2", "p3", "p4", "p5"]:
        offset = _patient_offset(pid)
        assert -max_days <= offset <= max_days


def test_shift_date_preserves_gap():
    pid = "patient-gap-test"
    d1 = date(2024, 1, 1)
    d2 = date(2024, 3, 15)
    gap_before = (d2 - d1).days
    s1 = shift_date(d1, pid)
    s2 = shift_date(d2, pid)
    gap_after = (s2 - s1).days
    assert gap_before == gap_after


def test_shift_iso_dates_in_text():
    pid = "test-patient-999"
    text = "Patient admitted on 2024-01-15. Follow-up on 2024-03-20."
    shifted = shift_dates_in_text(text, pid)
    assert "2024-01-15" not in shifted
    assert "2024-03-20" not in shifted
    assert shifted.count("-") >= 2


def test_non_date_content_unchanged():
    pid = "test-patient-xyz"
    text = "eGFR: 45 mL/min/1.73m2. HbA1c: 7.2%. Creatinine: 1.4 mg/dL."
    shifted = shift_dates_in_text(text, pid)
    assert "45" in shifted
    assert "7.2" in shifted
    assert "1.4" in shifted
