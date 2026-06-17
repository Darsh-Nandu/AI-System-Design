"""Transaction service -- queries the DB for eligible transactions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from refund_agent.models import Transaction
from refund_agent.storage.postgres import AsyncSessionFactory, TransactionORM


class TransactionService:
    async def get_eligible_transactions(
        self,
        user_id: str,
        days: int = 30,
        merchant_filter: str | None = None,
    ) -> list[Transaction]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        async with AsyncSessionFactory() as session:
            q = (
                select(TransactionORM)
                .where(
                    TransactionORM.user_id == user_id,
                    TransactionORM.created_at >= cutoff,
                    TransactionORM.refunded == False,  # noqa: E712
                    TransactionORM.refund_eligible == True,  # noqa: E712
                )
                .order_by(TransactionORM.created_at.desc())
            )
            if merchant_filter:
                q = q.where(TransactionORM.merchant.ilike(f"%{merchant_filter}%"))

            rows = await session.scalars(q)
            return [_orm_to_model(r) for r in rows.all()]

    async def get_transaction(self, txn_id: str) -> Transaction | None:
        async with AsyncSessionFactory() as session:
            row = await session.get(TransactionORM, txn_id)
            if not row:
                return None
            return _orm_to_model(row)

    async def mark_refunded(self, txn_id: str) -> None:
        from sqlalchemy import update

        async with AsyncSessionFactory() as session:
            await session.execute(
                update(TransactionORM)
                .where(TransactionORM.id == txn_id)
                .values(refunded=True, refunded_at=datetime.now(timezone.utc))
            )
            await session.commit()


def _orm_to_model(orm: TransactionORM) -> Transaction:
    return Transaction(
        id=str(orm.id),
        user_id=str(orm.user_id),
        amount=orm.amount,
        currency=orm.currency,
        merchant=orm.merchant,
        description=orm.description,
        created_at=orm.created_at,
        refunded=orm.refunded,
        refund_eligible=orm.refund_eligible,
    )
