"""Temporal Cypher traversal queries for the medical KG."""

from __future__ import annotations

from typing import Any

import structlog

from medical_rag.knowledge_graph.neo4j_client import run_query

log = structlog.get_logger(__name__)


async def get_active_drugs(patient_id: str, top_k: int = 20) -> list[dict[str, Any]]:
    """Return all drugs ever prescribed, most recent first."""
    return await run_query(
        """
        MATCH (p:Patient {id: $pid})-[r:PRESCRIBED]->(d:Drug)
        RETURN d.name AS drug_name, d.rxnorm_id AS rxnorm, r.date AS prescribed_date
        ORDER BY r.date DESC
        LIMIT $top_k
        """,
        {"pid": patient_id, "top_k": top_k},
    )


async def get_lab_trend(patient_id: str, test_name: str) -> list[dict[str, Any]]:
    """Return chronological lab values for a given test (for trend analysis)."""
    return await run_query(
        """
        MATCH (p:Patient {id: $pid})-[:HAS_LAB]->(l:LabValue {name: $test})
        RETURN l.value AS value, l.unit AS unit, l.date AS date
        ORDER BY l.date ASC
        """,
        {"pid": patient_id, "test": test_name},
    )


async def get_conditions_timeline(patient_id: str) -> list[dict[str, Any]]:
    """Return all diagnoses with date."""
    return await run_query(
        """
        MATCH (p:Patient {id: $pid})-[r:DIAGNOSED_WITH]->(c:Condition)
        RETURN c.name AS condition, c.icd_code AS icd_code, r.date AS diagnosed_date
        ORDER BY r.date ASC
        """,
        {"pid": patient_id},
    )


async def get_temporal_context(patient_id: str) -> list[dict[str, Any]]:
    """Full timeline: drugs + labs + conditions ordered by date."""
    return await run_query(
        """
        MATCH (p:Patient {id: $pid})
        OPTIONAL MATCH (p)-[r1:PRESCRIBED]->(d:Drug)
        OPTIONAL MATCH (p)-[r2:HAS_LAB]->(l:LabValue)
        OPTIONAL MATCH (p)-[r3:DIAGNOSED_WITH]->(c:Condition)
        WITH
          collect(DISTINCT {type: 'drug', name: d.name, date: r1.date}) AS drugs,
          collect(DISTINCT {type: 'lab', name: l.name, value: l.value, unit: l.unit, date: l.date}) AS labs,
          collect(DISTINCT {type: 'condition', name: c.name, icd: c.icd_code, date: r3.date}) AS conditions
        RETURN drugs + labs + conditions AS events
        """,
        {"pid": patient_id},
    )


async def get_drug_lab_correlation(
    patient_id: str, drug_name: str, lab_name: str
) -> list[dict[str, Any]]:
    """Find lab values before and after a drug was prescribed (causal analysis)."""
    return await run_query(
        """
        MATCH (p:Patient {id: $pid})-[rx:PRESCRIBED]->(d:Drug)
        WHERE toLower(d.name) = toLower($drug)
        WITH p, rx.date AS rx_date
        MATCH (p)-[:HAS_LAB]->(l:LabValue)
        WHERE toLower(l.name) = toLower($lab)
        RETURN
          l.value AS value,
          l.unit AS unit,
          l.date AS date,
          CASE WHEN l.date < rx_date THEN 'before' ELSE 'after' END AS phase
        ORDER BY l.date ASC
        """,
        {"pid": patient_id, "drug": drug_name, "lab": lab_name},
    )


async def get_lab_deltas(patient_id: str, test_name: str) -> list[dict[str, Any]]:
    """Return consecutive lab pairs with delta values (for trend alerting)."""
    return await run_query(
        """
        MATCH (p:Patient {id: $pid})-[:HAS_LAB]->(prev:LabValue)-[e:PRECEDED]->(nxt:LabValue)
        WHERE toLower(prev.name) = toLower($test) AND toLower(nxt.name) = toLower($test)
        RETURN
          prev.value AS prev_value,
          nxt.value AS curr_value,
          nxt.value - prev.value AS delta,
          e.delta_days AS days_between,
          nxt.date AS date
        ORDER BY nxt.date ASC
        """,
        {"pid": patient_id, "test": test_name},
    )


async def get_kg_summary_for_query(patient_id: str, query: str) -> str:
    """Generate a text summary of KG facts relevant to the query."""
    drugs = await get_active_drugs(patient_id, top_k=10)
    conditions = await get_conditions_timeline(patient_id)

    drug_lines = [
        f"Drug: {d['drug_name']} (prescribed {d['prescribed_date']})"
        for d in drugs if d.get("drug_name")
    ]
    condition_lines = [
        f"Condition: {c['condition']} [{c.get('icd_code', '')}] (diagnosed {c['diagnosed_date']})"
        for c in conditions if c.get("condition")
    ]

    egfr_trend = await get_lab_trend(patient_id, "eGFR")
    egfr_lines = [
        f"eGFR: {r['value']} {r['unit']} on {r['date']}"
        for r in egfr_trend[-3:]
    ]

    all_lines = condition_lines + drug_lines + egfr_lines
    return "\n".join(all_lines) if all_lines else "No KG data available for this patient."
