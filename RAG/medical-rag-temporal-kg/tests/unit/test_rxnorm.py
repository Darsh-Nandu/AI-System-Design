"""Tests for RxNorm drug interaction rules engine."""

from __future__ import annotations

import pytest

from medical_rag.knowledge_graph.rxnorm import check_interactions
from medical_rag.models import Severity


def test_metformin_low_egfr_warning():
    warnings = check_interactions(["metformin"], lab_values={"egfr": 25.0})
    assert len(warnings) >= 1
    w = warnings[0]
    assert "metformin" in w.drug_a
    assert w.severity in (Severity.HIGH, Severity.CRITICAL)


def test_metformin_normal_egfr_no_warning():
    warnings = check_interactions(["metformin"], lab_values={"egfr": 65.0})
    egfr_warnings = [w for w in warnings if "egfr" in w.drug_b.lower()]
    assert len(egfr_warnings) == 0


def test_warfarin_aspirin_interaction():
    warnings = check_interactions(["warfarin", "aspirin"])
    assert any("warfarin" in w.drug_a for w in warnings)


def test_alias_resolution_lisinopril_nsaid():
    warnings = check_interactions(["lisinopril", "ibuprofen"])
    assert len(warnings) >= 1


def test_no_interactions_for_single_safe_drug():
    warnings = check_interactions(["amoxicillin"])
    assert warnings == []


def test_ssri_tramadol_flagged():
    warnings = check_interactions(["sertraline", "tramadol"])
    assert len(warnings) >= 1
    severities = {w.severity for w in warnings}
    assert Severity.HIGH in severities
