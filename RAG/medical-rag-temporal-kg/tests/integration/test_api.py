"""Integration tests for the FastAPI application."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

SKIP = os.getenv("SKIP_INTEGRATION", "1") == "1"

pytestmark = pytest.mark.skipif(SKIP, reason="SKIP_INTEGRATION=1")


@pytest.fixture
async def client():
    from medical_rag.api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_ingest_and_query(client: AsyncClient) -> None:
    ingest_payload = {
        "patient_id": "int-test-patient-001",
        "requester_id": "test-doctor",
        "documents": [
            {
                "modality": "lab",
                "date": "2024-01-15",
                "source_id": "lab-001",
                "labs": [
                    {"test_name": "eGFR", "value": 42, "unit": "mL/min/1.73m2"},
                    {"test_name": "creatinine", "value": 1.9, "unit": "mg/dL"},
                ],
            },
            {
                "modality": "text",
                "date": "2024-01-16",
                "source_id": "clinical-note-001",
                "content": "Patient has Stage 3 CKD and Type 2 Diabetes. Currently on metformin 1000mg BD.",
            },
        ],
    }

    resp = await client.post("/ingest", json=ingest_payload)
    assert resp.status_code == 202
    data = resp.json()
    assert data["findings_ingested"] == 2

    query_payload = {
        "patient_id": "int-test-patient-001",
        "query": "Is metformin safe given the current kidney function?",
        "requester_id": "test-doctor",
    }
    resp = await client.post("/query", json=query_payload)
    assert resp.status_code == 200
    result = resp.json()
    assert "generated_answer" in result
    assert result["patient_id"] == "int-test-patient-001"
    assert 0.0 <= result["faithfulness_score"] <= 1.0


async def test_audit_list_entries(client: AsyncClient) -> None:
    resp = await client.get("/audit/entries?limit=10")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_audit_verify_chain(client: AsyncClient) -> None:
    resp = await client.get("/audit/verify?limit=100")
    assert resp.status_code == 200
    data = resp.json()
    assert "chain_ok" in data
    assert "violations" in data
