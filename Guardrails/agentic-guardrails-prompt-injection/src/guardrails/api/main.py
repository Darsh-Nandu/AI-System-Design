"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from guardrails.api.routes import egress, events, scan, tools
from guardrails.api.schemas import HealthOut
from guardrails.audit.security_log import create_tables
from guardrails.config import get_settings

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("startup_begin")
    await create_tables()
    log.info("startup_complete")
    yield
    log.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agentic Guardrails & Prompt Injection Defense",
        version="0.1.0",
        description="6-layer defense-in-depth for LLM agents: regex, ML classifier, LLM guard, content sanitization, tool validation, egress scanning",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scan.router)
    app.include_router(tools.router)
    app.include_router(egress.router)
    app.include_router(events.router)

    app.mount("/metrics", make_asgi_app())

    @app.get("/health", response_model=HealthOut, tags=["health"])
    async def health() -> HealthOut:
        return HealthOut()

    return app


app = create_app()


def run() -> None:
    cfg = get_settings()
    uvicorn.run(
        "guardrails.api.main:app",
        host=cfg.api_host,
        port=cfg.api_port,
        workers=1,
        reload=False,
    )
