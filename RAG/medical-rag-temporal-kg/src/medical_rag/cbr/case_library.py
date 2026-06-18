"""Case-Based Reasoning: ANN search over anonymized patient timelines."""

from __future__ import annotations

import structlog

from medical_rag.cbr.timeline_encoder import encode_timeline
from medical_rag.models import CBRMatch, PatientTimeline
from medical_rag.storage.qdrant_store import index_timeline, search_similar_timelines

log = structlog.get_logger(__name__)


async def register_timeline(timeline: PatientTimeline) -> None:
    """Index a de-identified patient timeline into the case library."""
    summary = encode_timeline(timeline)
    await index_timeline(timeline, summary)
    log.info("cbr_timeline_indexed", patient_id=timeline.patient_id, summary_len=len(summary))


async def find_similar_cases(
    query_timeline: PatientTimeline,
    top_k: int = 5,
) -> list[CBRMatch]:
    """ANN search for similar historical cases."""
    query_text = encode_timeline(query_timeline)
    results = await search_similar_timelines(
        query_text=query_text,
        exclude_patient=query_timeline.patient_id,
        top_k=top_k,
    )

    matches: list[CBRMatch] = []
    for r in results:
        summary = r.get("summary", "")
        score = float(r.get("score", 0.0))
        matches.append(CBRMatch(
            case_id=r.get("patient_id", "unknown"),
            similarity_score=score,
            patient_profile_summary=summary[:300],
            outcome_summary="[Outcome data available in de-identified clinical record]",
            num_similar_patients=1,
        ))
    return matches
