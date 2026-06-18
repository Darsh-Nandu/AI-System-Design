"""Full end-to-end query pipeline.

Stages:
1. Query decomposition (sub-queries + metadata filters)
2. Two-tier retrieval per sub-query, merge results
3. Cross-encoder re-ranking
4. CRAG verification
5. Constrained generation
6. Faithfulness checking
"""

from __future__ import annotations

import time
from typing import Any

from rag.generation.faithfulness import check_faithfulness
from rag.generation.generator import generate_answer
from rag.logging import get_logger
from rag.metrics import queries_total, query_latency
from rag.models import RAGResponse, ScoredChunk
from rag.pipeline.query_decomposer import decompose_query
from rag.retrieval.crag_verifier import verify_chunks
from rag.retrieval.metadata_filter import extract_filters_from_sub_query
from rag.retrieval.reranker import rerank
from rag.retrieval.two_tier_search import TwoTierSearch

logger = get_logger(__name__)


class QueryPipeline:
    def __init__(self) -> None:
        self._search = TwoTierSearch()

    async def run(
        self,
        query: str,
        metadata_filter: dict[str, Any] | None = None,
    ) -> RAGResponse:
        t0 = time.perf_counter()

        try:
            decomposition = await decompose_query(query)

            if decomposition.clarification_needed:
                queries_total.labels(status="clarification_needed").inc()
                return RAGResponse(
                    query=query,
                    answer=f"Your query needs clarification: {decomposition.clarification_reason}",
                    decomposition=decomposition,
                )

            # Retrieve for all sub-queries and merge (dedup by chunk_id)
            seen_ids: set[str] = set()
            all_chunks: list[ScoredChunk] = []

            for sub_q in decomposition.sub_queries:
                sub_filter = {**(metadata_filter or {})}
                sub_filter.update(extract_filters_from_sub_query(sub_q.metadata_filters))

                results = await self._search.search(
                    query=sub_q.text,
                    metadata_filter=sub_filter or None,
                )
                for sc in results:
                    if sc.chunk.id not in seen_ids:
                        seen_ids.add(sc.chunk.id)
                        all_chunks.append(sc)

            logger.info("retrieval_merged", chunks=len(all_chunks), sub_queries=len(decomposition.sub_queries))

            # Re-rank all merged chunks against the original query
            reranked = await rerank(query, all_chunks)

            # CRAG verification
            verified = await verify_chunks(query, reranked)

            if not verified:
                queries_total.labels(status="no_relevant_chunks").inc()
                return RAGResponse(
                    query=query,
                    answer="The provided documents do not contain sufficient information to answer this question.",
                    retrieved_chunk_count=len(all_chunks),
                    chunks_passed_crag=0,
                    decomposition=decomposition,
                )

            # Constrained generation
            answer = await generate_answer(query, verified)

            # Faithfulness check
            claims, f_score = await check_faithfulness(answer, verified)
            ungrounded = [c.sentence for c in claims if not c.grounded]
            citations = list({c.citation for c in claims if c.citation and c.grounded})

            elapsed = time.perf_counter() - t0
            query_latency.observe(elapsed)
            queries_total.labels(status="success").inc()

            logger.info("query_completed", latency=round(elapsed, 3), faithfulness=round(f_score, 3))

            return RAGResponse(
                query=query,
                answer=answer,
                citations=citations,
                cited_claims=claims,
                faithfulness_score=f_score,
                ungrounded_claims=ungrounded,
                retrieved_chunk_count=len(all_chunks),
                chunks_passed_crag=len(verified),
                decomposition=decomposition,
            )

        except Exception as exc:
            queries_total.labels(status="error").inc()
            logger.exception("query_pipeline_failed", error=str(exc))
            return RAGResponse(
                query=query,
                answer="An internal error occurred. Please try again.",
                faithfulness_score=0.0,
            )
