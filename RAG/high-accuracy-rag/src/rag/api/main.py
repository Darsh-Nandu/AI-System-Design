"""FastAPI application for the high-accuracy RAG system."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from rag.api.routes import documents, query
from rag.api.schemas import HealthResponse
from rag.logging import configure_logging
from rag.storage.postgres import create_tables
from rag.storage.qdrant_store import QdrantStore

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    await create_tables()
    store = QdrantStore()
    await store.ensure_collections()
    logger.info("high_accuracy_rag_started")
    yield
    logger.info("high_accuracy_rag_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="High-Accuracy Legal RAG",
        description="Two-tier retrieval with CRAG verification and faithfulness checking for legal documents.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(query.router)
    app.include_router(documents.router)

    app.mount("/metrics", make_asgi_app())

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    async def health() -> HealthResponse:
        return HealthResponse()

    return app


app = create_app()


def run() -> None:
    import uvicorn
    from rag.config import get_settings
    s = get_settings()
    uvicorn.run("rag.api.main:app", host="0.0.0.0", port=s.api_port, reload=False)
