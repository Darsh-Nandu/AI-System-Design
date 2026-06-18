"""Async Neo4j client wrapper with connection pooling."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver

from medical_rag.config import get_settings

log = structlog.get_logger(__name__)

_driver: AsyncDriver | None = None


async def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        cfg = get_settings()
        _driver = AsyncGraphDatabase.driver(
            cfg.neo4j_uri,
            auth=(cfg.neo4j_user, cfg.neo4j_password),
            max_connection_pool_size=10,
        )
        log.info("neo4j_driver_created", uri=cfg.neo4j_uri)
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


@asynccontextmanager
async def session() -> AsyncGenerator[Any, None]:
    driver = await get_driver()
    async with driver.session() as s:
        yield s


async def run_query(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    async with session() as s:
        result = await s.run(cypher, params or {})
        records = await result.data()
        return records


async def initialize_schema() -> None:
    constraints = [
        "CREATE CONSTRAINT patient_id IF NOT EXISTS FOR (p:Patient) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT condition_id IF NOT EXISTS FOR (c:Condition) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT drug_rxnorm IF NOT EXISTS FOR (d:Drug) REQUIRE d.rxnorm_id IS UNIQUE",
        "CREATE CONSTRAINT lab_id IF NOT EXISTS FOR (l:LabValue) REQUIRE l.id IS UNIQUE",
        "CREATE CONSTRAINT procedure_id IF NOT EXISTS FOR (pr:Procedure) REQUIRE pr.id IS UNIQUE",
        "CREATE CONSTRAINT symptom_id IF NOT EXISTS FOR (s:Symptom) REQUIRE s.id IS UNIQUE",
    ]
    indexes = [
        "CREATE INDEX patient_idx IF NOT EXISTS FOR (p:Patient) ON (p.id)",
        "CREATE INDEX drug_name_idx IF NOT EXISTS FOR (d:Drug) ON (d.name)",
        "CREATE INDEX lab_date_idx IF NOT EXISTS FOR (l:LabValue) ON (l.date)",
        "CREATE INDEX condition_icd_idx IF NOT EXISTS FOR (c:Condition) ON (c.icd_code)",
    ]
    for stmt in constraints + indexes:
        try:
            await run_query(stmt)
        except Exception as exc:
            log.warning("schema_init_warning", stmt=stmt[:60], error=str(exc))
    log.info("neo4j_schema_initialized")
