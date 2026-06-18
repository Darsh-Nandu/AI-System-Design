"""Run a sample query through the full pipeline."""

from __future__ import annotations

import asyncio
import sys

from rag.logging import configure_logging
from rag.pipeline.query import QueryPipeline
from rag.storage.postgres import create_tables
from rag.storage.qdrant_store import QdrantStore

configure_logging()


async def _run(query: str) -> None:
    await create_tables()
    store = QdrantStore()
    await store.ensure_collections()

    pipeline = QueryPipeline()
    result = await pipeline.run(query)

    print(f"\nQuery: {result.query}")
    print(f"\nAnswer:\n{result.answer}")
    print(f"\nFaithfulness score: {result.faithfulness_score:.2f}")
    print(f"Retrieved: {result.retrieved_chunk_count} chunks | Passed CRAG: {result.chunks_passed_crag}")

    if result.citations:
        print(f"\nCitations:")
        for c in result.citations:
            print(f"  - {c}")

    if result.ungrounded_claims:
        print(f"\nFlagged (ungrounded):")
        for claim in result.ungrounded_claims:
            print(f"  ! {claim[:100]}")

    if result.decomposition:
        d = result.decomposition
        print(f"\nDecomposed into {len(d.sub_queries)} sub-queries:")
        for sq in d.sub_queries:
            print(f"  - {sq.text}")
            if sq.metadata_filters:
                print(f"    filters: {sq.metadata_filters}")


def main() -> None:
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "software company held liable for data breach affecting more than 10000 users in India"
    )
    asyncio.run(_run(query))


if __name__ == "__main__":
    main()
