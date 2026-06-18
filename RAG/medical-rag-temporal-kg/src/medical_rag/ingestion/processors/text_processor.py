"""Biomedical NLP processor using Claude for entity extraction."""

from __future__ import annotations

import json
from datetime import date

import anthropic
import structlog

from medical_rag.config import get_settings
from medical_rag.models import MedicalEntity, MedicalFinding, ModalityType, Severity

log = structlog.get_logger(__name__)

_EXTRACTION_PROMPT = """\
Extract all clinical entities from the following medical text. Return a JSON object with:
- entities: list of {entity_type, value, normalized, icd_code, rxnorm_id, confidence}
  entity_type must be one of: CONDITION, DRUG, PROCEDURE, SYMPTOM, MEASUREMENT, FINDING
- is_abnormal: boolean - does the text describe any abnormal findings?
- severity: one of critical/high/moderate/low/normal
- specialist_flags: list of specialties that should be consulted (e.g. nephrology, cardiology)

Medical text:
{text}

Respond ONLY with valid JSON. No markdown, no explanation."""


async def process_text(
    text: str, patient_id: str, source_doc: str, finding_date: date
) -> MedicalFinding:
    cfg = get_settings()
    client = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)

    entities: list[MedicalEntity] = []
    is_abnormal = False
    severity = Severity.NORMAL
    specialist_flags: list[str] = []
    confidence = 0.85

    try:
        response = await client.messages.create(
            model=cfg.llm_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": _EXTRACTION_PROMPT.format(text=text)}],
        )
        raw = response.content[0].text.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]

        data = json.loads(raw)
        for ent in data.get("entities", []):
            entities.append(MedicalEntity(
                entity_type=ent.get("entity_type", "FINDING"),
                value=ent.get("value", ""),
                normalized=ent.get("normalized"),
                icd_code=ent.get("icd_code"),
                rxnorm_id=ent.get("rxnorm_id"),
                confidence=float(ent.get("confidence", 0.9)),
            ))
        is_abnormal = bool(data.get("is_abnormal", False))
        sev_raw = data.get("severity", "normal").lower()
        severity = Severity(sev_raw) if sev_raw in Severity._value2member_map_ else Severity.NORMAL
        specialist_flags = data.get("specialist_flags", [])

        log.info("text_processor_done", patient_id=patient_id, entities=len(entities))
    except Exception as exc:
        log.warning("text_processor_error", error=str(exc))
        confidence = 0.5

    return MedicalFinding(
        patient_id=patient_id,
        modality=ModalityType.TEXT,
        finding_date=finding_date,
        source_document=source_doc,
        entities=entities,
        raw_text=text,
        confidence=confidence,
        is_abnormal=is_abnormal,
        severity=severity,
        specialist_flags=specialist_flags,
    )
