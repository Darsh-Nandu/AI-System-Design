"""Run a clinical query against the seeded patient.

Usage:
  python -m example.run_query
  python -m example.run_query "Is metformin still safe?"
"""

from __future__ import annotations

import asyncio
import json
import sys

import httpx

PATIENT_ID = "demo-patient-raj-sharma-001"
API_URL = "http://localhost:8085"

DEFAULT_QUERY = (
    "Is metformin still safe for this patient given the declining kidney function? "
    "What dose adjustments should be considered and are there any drug interaction concerns?"
)

QUERIES = [
    DEFAULT_QUERY,
    "What is the trend in this patient's eGFR over the past year?",
    "Are there any drug interactions between the current medications?",
    "What specialist consultations are recommended based on the clinical findings?",
]


def _print_response(result: dict) -> None:
    print("\n" + "=" * 70)
    print(f"QUERY: {result['query']}")
    print("=" * 70)

    if result.get("drug_warnings"):
        print("\nDRUG INTERACTION WARNINGS:")
        for w in result["drug_warnings"]:
            print(f"  [{w['severity'].upper()}] {w['drug_a']} + {w['drug_b']}")
            print(f"  -> {w['recommendation']}")
            print(f"  Source: {w['rxnorm_source']}")

    print(f"\nFAITHFULNESS SCORE: {result['faithfulness_score']:.2%}")

    high = result.get("high_confidence_evidence", [])
    med = result.get("medium_confidence_evidence", [])
    if high:
        print(f"\nHIGH CONFIDENCE EVIDENCE ({len(high)} items):")
        for ev in high[:2]:
            print(f"  [{ev['source_type']}] {ev['content'][:120]}...")
    if med:
        print(f"\nMEDIUM CONFIDENCE EVIDENCE ({len(med)} items):")
        for ev in med[:2]:
            print(f"  [{ev['source_type']}] {ev['content'][:120]}...")

    if result.get("specialist_consults"):
        print(f"\nSPECIALIST CONSULTS RECOMMENDED: {', '.join(result['specialist_consults'])}")

    print("\nCLINICAL ANALYSIS:")
    print(result.get("generated_answer", "No answer generated"))

    if result.get("ungrounded_sentences"):
        print(f"\nWARNING: {len(result['ungrounded_sentences'])} ungrounded sentences removed")

    print(f"\n{result['disclaimer']}")
    print("=" * 70)


async def main() -> None:
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_QUERY

    async with httpx.AsyncClient(timeout=120) as client:
        print(f"Querying patient {PATIENT_ID}...")
        resp = await client.post(
            f"{API_URL}/query",
            json={
                "patient_id": PATIENT_ID,
                "query": query,
                "requester_id": "demo-doctor",
            },
        )
        resp.raise_for_status()
        _print_response(resp.json())


if __name__ == "__main__":
    asyncio.run(main())
