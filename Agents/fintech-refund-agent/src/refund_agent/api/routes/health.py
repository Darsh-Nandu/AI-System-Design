"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from refund_agent.api.schemas import HealthResponse
from refund_agent.storage.postgres import AsyncSessionFactory
from refund_agent.storage.redis_client import get_redis

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    services: dict[str, str] = {}

    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception as exc:
        services["postgres"] = f"error: {exc}"

    try:
        redis = await get_redis()
        await redis.ping()
        services["redis"] = "ok"
    except Exception as exc:
        services["redis"] = f"error: {exc}"

    overall = "healthy" if all(v == "ok" for v in services.values()) else "degraded"
    return HealthResponse(status=overall, version="0.1.0", services=services)
