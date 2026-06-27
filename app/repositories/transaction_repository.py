import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.models.job_summary import JobSummary


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_job_id(self, job_id: uuid.UUID) -> list[Transaction]:
        result = await self.session.execute(
            select(Transaction)
            .where(Transaction.job_id == job_id)
            .order_by(Transaction.txn_date)
        )
        return list(result.scalars().all())

    async def get_anomalies_by_job_id(self, job_id: uuid.UUID) -> list[Transaction]:
        result = await self.session.execute(
            select(Transaction)
            .where(Transaction.job_id == job_id, Transaction.is_anomaly.is_(True))
            .order_by(Transaction.amount.desc())
        )
        return list(result.scalars().all())


class SummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_job_id(self, job_id: uuid.UUID) -> JobSummary | None:
        result = await self.session.execute(
            select(JobSummary).where(JobSummary.job_id == job_id)
        )
        return result.scalar_one_or_none()
