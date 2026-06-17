"""PostgreSQL ORM -- SQLAlchemy 2.0 async."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from refund_agent.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


class TransactionORM(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    merchant: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refunded: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refund_eligible: Mapped[bool] = mapped_column(Boolean, default=True)


class RefundSessionORM(Base):
    __tablename__ = "refund_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_count: Mapped[int] = mapped_column(default=0)
    total_refunded: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    escalation_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    human_ticket_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AuditEntryORM(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_version: Mapped[str] = mapped_column(String(64), default="refund-agent-v0.1.0")
    decision: Mapped[str] = mapped_column(String(64), default="")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


class EscalationTicketORM(Base):
    __tablename__ = "escalation_tickets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transaction_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)


_engine = create_async_engine(
    settings.postgres_dsn,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionFactory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session


async def create_tables() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed() -> None:
    """Seed sample transactions for local development and testing."""
    from datetime import timedelta, timezone

    async with AsyncSessionFactory() as session:
        now = datetime.now(timezone.utc)
        sample_txns = [
            TransactionORM(
                id=f"txn_{i:04d}",
                user_id="user_demo",
                amount=Decimal(str(amount)),
                currency="USD",
                merchant=merchant,
                description=description,
                created_at=now - timedelta(days=days_ago),
                refunded=False,
                refund_eligible=True,
            )
            for i, (amount, merchant, description, days_ago) in enumerate([
                (49.99, "Zomato", "Order #4821 -- Biryani", 3),
                (129.00, "Myntra", "Order #9923 -- Sneakers", 7),
                (15.50, "Swiggy", "Order #3310 -- Pizza", 1),
                (299.00, "Flipkart", "Order #7811 -- Headphones", 15),
                (75.00, "BookMyShow", "Concert tickets #2201", 20),
                (599.00, "Amazon", "Order #5512 -- Tablet", 25),  # will trigger magnitude check
                (9.99, "Netflix", "Monthly subscription", 5),
            ])
        ]
        for txn in sample_txns:
            existing = await session.get(TransactionORM, txn.id)
            if not existing:
                session.add(txn)
        await session.commit()
        print(f"Seeded {len(sample_txns)} sample transactions for user_demo")
