"""Integration tests for the FastAPI layer.

Requires running infrastructure (postgres, qdrant, redis).
Run with: pytest tests/integration -v
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from news_aggregator.api.main import app


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
@pytest.mark.integration
async def test_health_endpoint(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "services" in data


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_empty_query_rejected(client: AsyncClient):
    response = await client.post("/articles/search", json={"query": "", "limit": 10})
    assert response.status_code == 422  # pydantic validation error


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_returns_results_shape(client: AsyncClient):
    response = await client.post(
        "/articles/search",
        json={"query": "climate change policy", "limit": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert "articles" in data
    assert "total" in data
    assert isinstance(data["articles"], list)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_nonexistent_article(client: AsyncClient):
    from uuid import uuid4
    response = await client.get(f"/articles/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ingest_article(client: AsyncClient):
    payload = {
        "url": "https://test.example.com/article-integration-test",
        "source": "Test Source",
        "title": "Integration Test Article About Climate Policy",
        "body": "This is a test article body about climate change and environmental policy.",
        "published_at": "2024-11-01T14:00:00Z",
        "tags": ["test", "climate"],
    }
    response = await client.post("/articles/ingest", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert "status" in data
    assert data["status"] in ("accepted", "duplicate", "clustered")
