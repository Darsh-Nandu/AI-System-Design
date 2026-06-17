"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from news_aggregator.api.schemas import HealthResponse
from news_aggregator.storage.postgres import AsyncSessionFactory
from news_aggregator.storage.qdrant import QdrantStore
from news_aggregator.storage.redis_client import RedisStore

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    services: dict[str, str] = {}

    # Postgres
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception as e:
        services["postgres"] = f"error: {e}"

    # Redis
    try:
        redis = RedisStore()
        await redis._client.ping()
        await redis.close()
        services["redis"] = "ok"
    except Exception as e:
        services["redis"] = f"error: {e}"

    # Qdrant
    try:
        qdrant = QdrantStore()
        await qdrant._client.get_collections()
        await qdrant.close()
        services["qdrant"] = "ok"
    except Exception as e:
        services["qdrant"] = f"error: {e}"

    overall = "healthy" if all(v == "ok" for v in services.values()) else "degraded"
    return HealthResponse(status=overall, version="0.1.0", services=services)
