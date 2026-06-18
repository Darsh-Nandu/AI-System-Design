"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from medical_rag.api.routes import audit, ingest, query
from medical_rag.api.schemas import HealthOut
from medical_rag.audit.audit_log import AuditEntryORM
from medical_rag.config import get_settings
from medical_rag.knowledge_graph.neo4j_client import close_driver, initialize_schema
from medical_rag.storage.postgres import Base, PatientORM, IngestionRecordORM, QueryRecordORM, create_tables
from medical_rag.storage.qdrant_store import initialize_collections

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("startup_begin")
    await create_tables()
    await initialize_collections()
    try:
        await initialize_schema()
    except Exception as exc:
        log.warning("neo4j_schema_init_failed", error=str(exc))
    log.info("startup_complete")
    yield
    await close_driver()
    log.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Medical RAG with Temporal Knowledge Graph",
        version="0.1.0",
        description="HIPAA-compliant clinical decision support with Neo4j KG, multi-modal ingestion, and CBR",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ingest.router)
    app.include_router(query.router)
    app.include_router(audit.router)

    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    @app.get("/health", response_model=HealthOut, tags=["health"])
    async def health() -> HealthOut:
        return HealthOut()

    return app


app = create_app()


def run() -> None:
    cfg = get_settings()
    uvicorn.run(
        "medical_rag.api.main:app",
        host=cfg.api_host,
        port=cfg.api_port,
        workers=cfg.api_workers,
        reload=False,
    )
