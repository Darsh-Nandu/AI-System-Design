"""FastAPI application entry point."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from news_aggregator.api.routes import articles, health, stories
from news_aggregator.config import get_settings
from news_aggregator.logging import configure_logging, get_logger
from news_aggregator.storage.postgres import create_tables
from news_aggregator.storage.qdrant import QdrantStore

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    logger.info("api_starting")
    await create_tables()

    qdrant = QdrantStore()
    await qdrant.ensure_collections()
    await qdrant.close()

    logger.info("api_ready")
    yield
    logger.info("api_shutdown")


app = FastAPI(
    title="News Aggregator API",
    description="Production news aggregation pipeline — Kafka → spaCy → Qdrant → FastAPI",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_timing(request: Request, call_next: object) -> Response:
    start = time.monotonic()
    response: Response = await call_next(request)  # type: ignore[operator]
    duration = time.monotonic() - start
    response.headers["X-Process-Time"] = f"{duration:.4f}"
    return response


app.include_router(health.router)
app.include_router(articles.router)
app.include_router(stories.router)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def run() -> None:
    uvicorn.run(
        "news_aggregator.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=settings.api_workers,
        reload=False,
        access_log=True,
    )


if __name__ == "__main__":
    run()
