"""FastAPI application entry point."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from refund_agent.api.routes import chat, health, sessions
from refund_agent.config import get_settings
from refund_agent.logging import configure_logging, get_logger
from refund_agent.metrics import start_metrics_server
from refund_agent.storage.postgres import create_tables
from refund_agent.storage.redis_client import close_redis

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    logger.info("api_starting")
    await create_tables()
    start_metrics_server(port=9200)
    logger.info("api_ready")
    yield
    await close_redis()
    logger.info("api_shutdown")


app = FastAPI(
    title="Fintech Refund Agent",
    description="Safe irreversible action agent: LangGraph + Claude + idempotent execution",
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
async def add_timing(request: Request, call_next: object) -> Response:
    start = time.monotonic()
    response: Response = await call_next(request)  # type: ignore[operator]
    response.headers["X-Process-Time"] = f"{time.monotonic() - start:.4f}"
    return response


app.include_router(health.router)
app.include_router(chat.router)
app.include_router(sessions.router)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def run() -> None:
    uvicorn.run(
        "refund_agent.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        access_log=True,
    )


if __name__ == "__main__":
    run()
