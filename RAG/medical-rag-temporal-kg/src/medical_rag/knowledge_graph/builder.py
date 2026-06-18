"""Build the temporal knowledge graph from a PatientTimeline."""

from __future__ import annotations

import hashlib
from datetime import date

import structlog

from medical_rag.knowledge_graph.neo4j_client import run_query
from medical_rag.models import KGEdgeType, ModalityType, PatientTimeline

log = structlog.get_logger(__name__)


def _node_id(patient_id: str, entity_type: str, value: str) -> str:
    raw = f"{patient_id}:{entity_type}:{value.lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def upsert_patient(patient_id: str) -> None:
    await run_query(
        "MERGE (p:Patient {id: $pid}) ON CREATE SET p.created_at = datetime()",
        {"pid": patient_id},
    )


async def _upsert_condition(patient_id: str, name: str, icd_code: str | None, d: date) -> str:
    node_id = _node_id(patient_id, "condition", name)
    await run_query(
        """
        MERGE (c:Condition {id: $nid})
        ON CREATE SET c.name = $name, c.icd_code = $icd
        WITH c
        MATCH (p:Patient {id: $pid})
        MERGE (p)-[r:DIAGNOSED_WITH {date: $date}]->(c)
        """,
        {"nid": node_id, "name": name, "icd": icd_code or "", "pid": patient_id, "date": d.isoformat()},
    )
    return node_id


async def _upsert_drug(patient_id: str, name: str, rxnorm_id: str | None, d: date) -> str:
    node_id = _node_id(patient_id, "drug", name)
    await run_query(
        """
        MERGE (d:Drug {rxnorm_id: $rxnorm})
        ON CREATE SET d.name = $name
        SET d.name = $name
        WITH d
        MATCH (p:Patient {id: $pid})
        MERGE (p)-[r:PRESCRIBED {date: $date}]->(d)
        """,
        {
            "rxnorm": rxnorm_id or node_id,
            "name": name,
            "pid": patient_id,
            "date": d.isoformat(),
        },
    )
    return node_id


async def _upsert_lab(patient_id: str, test_name: str, value: float, unit: str, d: date) -> str:
    node_id = _node_id(patient_id, "lab", f"{test_name}:{d.isoformat()}")
    await run_query(
        """
        MERGE (l:LabValue {id: $nid})
        SET l.name = $name, l.value = $value, l.unit = $unit, l.date = $date
        WITH l
        MATCH (p:Patient {id: $pid})
        MERGE (p)-[:HAS_LAB]->(l)
        """,
        {"nid": node_id, "name": test_name, "value": value, "unit": unit, "date": d.isoformat(), "pid": patient_id},
    )
    return node_id


async def _upsert_symptom(patient_id: str, name: str, d: date) -> str:
    node_id = _node_id(patient_id, "symptom", name)
    await run_query(
        """
        MERGE (s:Symptom {id: $nid})
        ON CREATE SET s.name = $name
        WITH s
        MATCH (p:Patient {id: $pid})
        MERGE (p)-[r:HAS_SYMPTOM {date: $date}]->(s)
        """,
        {"nid": node_id, "name": name, "pid": patient_id, "date": d.isoformat()},
    )
    return node_id


async def _add_temporal_edges(patient_id: str) -> None:
    """Add PRECEDED edges between temporally adjacent lab values for the same test."""
    await run_query(
        """
        MATCH (p:Patient {id: $pid})-[:HAS_LAB]->(l:LabValue)
        WITH l ORDER BY l.name, l.date
        WITH collect(l) AS labs
        UNWIND range(0, size(labs)-2) AS i
        WITH labs[i] AS prev, labs[i+1] AS nxt
        WHERE prev.name = nxt.name
        MERGE (prev)-[r:PRECEDED]->(nxt)
        SET r.delta_days = duration.between(date(prev.date), date(nxt.date)).days
        """,
        {"pid": patient_id},
    )


async def build_from_timeline(timeline: PatientTimeline) -> None:
    patient_id = timeline.patient_id
    await upsert_patient(patient_id)

    for finding in timeline.sorted_findings():
        d = finding.finding_date

        if finding.modality == ModalityType.LAB:
            for lr in finding.lab_results:
                await _upsert_lab(patient_id, lr.test_name, lr.value, lr.unit, d)

        for entity in finding.entities:
            etype = entity.entity_type.upper()
            if etype == "CONDITION":
                await _upsert_condition(patient_id, entity.value, entity.icd_code, d)
            elif etype == "DRUG":
                await _upsert_drug(patient_id, entity.value, entity.rxnorm_id, d)
            elif etype == "SYMPTOM":
                await _upsert_symptom(patient_id, entity.value, d)

    await _add_temporal_edges(patient_id)
    log.info("kg_built", patient_id=patient_id, findings=len(timeline.findings))
