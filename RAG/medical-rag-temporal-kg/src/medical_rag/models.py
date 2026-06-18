"""Core domain models for medical RAG with temporal KG."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ModalityType(str, Enum):
    TEXT = "text"
    LAB = "lab"
    IMAGING = "imaging"
    ECG = "ecg"
    PATHOLOGY = "pathology"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    NORMAL = "normal"


class ConfidenceTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class KGNodeType(str, Enum):
    PATIENT = "Patient"
    CONDITION = "Condition"
    DRUG = "Drug"
    LAB_VALUE = "LabValue"
    PROCEDURE = "Procedure"
    SYMPTOM = "Symptom"


class KGEdgeType(str, Enum):
    DIAGNOSED_WITH = "DIAGNOSED_WITH"
    PRESCRIBED = "PRESCRIBED"
    UNDERWENT = "UNDERWENT"
    HAS_LAB = "HAS_LAB"
    HAS_SYMPTOM = "HAS_SYMPTOM"
    PRECEDED = "PRECEDED"
    CORRELATED_WITH = "CORRELATED_WITH"
    CONTRAINDICATED_BY = "CONTRAINDICATED_BY"
    RESULTED_IN = "RESULTED_IN"


class MedicalEntity(BaseModel):
    entity_type: str
    value: str
    normalized: str | None = None
    icd_code: str | None = None
    rxnorm_id: str | None = None
    loinc_code: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class LabResult(BaseModel):
    test_name: str
    loinc_code: str | None = None
    value: float
    unit: str
    reference_low: float | None = None
    reference_high: float | None = None
    is_abnormal: bool = False
    delta_from_previous: float | None = None
    severity: Severity = Severity.NORMAL


class MedicalFinding(BaseModel):
    finding_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str
    modality: ModalityType
    finding_date: date
    source_document: str
    entities: list[MedicalEntity] = Field(default_factory=list)
    lab_results: list[LabResult] = Field(default_factory=list)
    raw_text: str = ""
    structured_data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    is_abnormal: bool = False
    severity: Severity = Severity.NORMAL
    specialist_flags: list[str] = Field(default_factory=list)


class PatientTimeline(BaseModel):
    patient_id: str
    findings: list[MedicalFinding] = Field(default_factory=list)
    date_shift_days: int = 0

    def sorted_findings(self) -> list[MedicalFinding]:
        return sorted(self.findings, key=lambda f: f.finding_date)


class EvidenceItem(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_type: str
    source_id: str
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    tier: ConfidenceTier = ConfidenceTier.LOW
    finding_date: date | None = None
    specialist_flags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CBRMatch(BaseModel):
    case_id: str
    similarity_score: float
    patient_profile_summary: str
    outcome_summary: str
    num_similar_patients: int


class DrugInteractionWarning(BaseModel):
    drug_a: str
    drug_b: str
    interaction_type: str
    severity: Severity
    rxnorm_source: str
    recommendation: str


class MedicalRAGResponse(BaseModel):
    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str
    query: str
    high_confidence_evidence: list[EvidenceItem] = Field(default_factory=list)
    medium_confidence_evidence: list[EvidenceItem] = Field(default_factory=list)
    low_confidence_evidence: list[EvidenceItem] = Field(default_factory=list)
    cbr_matches: list[CBRMatch] = Field(default_factory=list)
    drug_warnings: list[DrugInteractionWarning] = Field(default_factory=list)
    generated_answer: str = ""
    specialist_consults: list[str] = Field(default_factory=list)
    ungrounded_sentences: list[str] = Field(default_factory=list)
    faithfulness_score: float = Field(default=1.0)
    disclaimer: str = (
        "This output is a clinical decision support tool and does not constitute medical advice. "
        "Always apply clinical judgment. Verify all information against primary sources."
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class IngestRequest(BaseModel):
    patient_id: str
    documents: list[dict[str, Any]]
    requester_id: str = "system"


class QueryRequest(BaseModel):
    patient_id: str
    query: str
    requester_id: str = "system"
    top_k_evidence: int = Field(default=10, ge=1, le=50)
