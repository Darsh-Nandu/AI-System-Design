"""FastAPI monitoring dashboard for the loop detection system."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from loop_detector.api.routes import checkpoints, sessions
from loop_detector.api.schemas import HealthOut
from loop_detector.logging import configure_logging
from loop_detector.storage.postgres import create_tables

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    await create_tables()
    logger.info("loop_detection_api_started")
    yield
    logger.info("loop_detection_api_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Loop Detection Monitor",
        description="Observability dashboard for the AI agent loop detection system.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(sessions.router)
    app.include_router(checkpoints.router)

    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    @app.get("/health", response_model=HealthOut, tags=["ops"])
    async def health() -> HealthOut:
        return HealthOut(status="ok")

    return app


app = create_app()
