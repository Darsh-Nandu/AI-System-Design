"""End-to-end pipeline: ingest and query."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from medical_rag.audit.audit_log import get_audit_logger
from medical_rag.cbr.case_library import find_similar_cases, register_timeline
from medical_rag.generation.faithfulness import check_faithfulness
from medical_rag.generation.generator import generate_answer
from medical_rag.generation.output_formatter import format_response
from medical_rag.ingestion.router import route_document
from medical_rag.ingestion.timeline import build_timeline
from medical_rag.knowledge_graph.builder import build_from_timeline
from medical_rag.models import IngestRequest, MedicalRAGResponse, PatientTimeline, QueryRequest
from medical_rag.retrieval.evidence_ranker import rank_evidence
from medical_rag.retrieval.hybrid_search import hybrid_retrieve
from medical_rag.storage.qdrant_store import index_finding

log = structlog.get_logger(__name__)


async def ingest_patient(request: IngestRequest) -> dict[str, Any]:
    patient_id = request.patient_id
    log.info("ingest_start", patient_id=patient_id, doc_count=len(request.documents))

    findings = []
    for i, doc in enumerate(request.documents):
        source_id = doc.get("source_id", f"doc_{i}")
        finding = await route_document(doc, patient_id, source_id)
        findings.append(finding)
        await index_finding(finding)

    timeline = build_timeline(patient_id, findings)

    await build_from_timeline(timeline)

    await register_timeline(timeline)

    audit = get_audit_logger()
    await audit.append(
        event_type="ingest",
        patient_id=patient_id,
        requester_id=request.requester_id,
        payload={
            "finding_count": len(findings),
            "doc_count": len(request.documents),
        },
    )

    log.info("ingest_complete", patient_id=patient_id, findings=len(findings))
    return {"patient_id": patient_id, "findings_ingested": len(findings)}


async def query_patient(request: QueryRequest) -> MedicalRAGResponse:
    patient_id = request.patient_id
    query = request.query
    log.info("query_start", patient_id=patient_id)

    evidence_raw, drug_warnings = await hybrid_retrieve(patient_id, query, top_k=request.top_k_evidence)
    evidence = rank_evidence(evidence_raw)

    dummy_timeline = PatientTimeline(patient_id=patient_id)
    cbr_matches = await find_similar_cases(dummy_timeline, top_k=5)

    raw_answer = await generate_answer(query, evidence)

    grounded_answer, ungrounded, faithfulness_score = await check_faithfulness(raw_answer, evidence)

    response = format_response(
        patient_id=patient_id,
        query=query,
        evidence=evidence,
        generated_answer=grounded_answer,
        ungrounded=ungrounded,
        faithfulness_score=faithfulness_score,
        drug_warnings=drug_warnings,
        cbr_matches=cbr_matches,
    )

    audit = get_audit_logger()
    await audit.append(
        event_type="query",
        patient_id=patient_id,
        requester_id=request.requester_id,
        payload={
            "query_id": response.query_id,
            "evidence_count": len(evidence),
            "faithfulness": faithfulness_score,
            "drug_warnings": len(drug_warnings),
            "specialist_consults": response.specialist_consults,
        },
    )

    log.info(
        "query_complete",
        patient_id=patient_id,
        query_id=response.query_id,
        faithfulness=faithfulness_score,
    )
    return response
