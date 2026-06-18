"""FastAPI dashboard for the coding assistant eval pipeline."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from eval_pipeline.api.routes import runs
from eval_pipeline.api.schemas import HealthOut
from eval_pipeline.logging import configure_logging
from eval_pipeline.storage.postgres import create_tables

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    await create_tables()
    logger.info("eval_pipeline_api_started")
    yield
    logger.info("eval_pipeline_api_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Coding Assistant Eval Pipeline",
        description="Model upgrade regression detection via production log replay.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(runs.router)

    app.mount("/metrics", make_asgi_app())

    @app.get("/health", response_model=HealthOut, tags=["ops"])
    async def health() -> HealthOut:
        return HealthOut()

    return app


app = create_app()


def run() -> None:
    import uvicorn
    from eval_pipeline.config import get_settings
    settings = get_settings()
    uvicorn.run("eval_pipeline.api.main:app", host="0.0.0.0", port=settings.api_port, reload=False)
