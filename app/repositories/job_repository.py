import uuid
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.domain.enums import JobStatus


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, original_filename: str) -> Job:
        job = Job(
            id=uuid.uuid4(),
            original_filename=original_filename,
            status=JobStatus.PENDING,
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        result = await self.session.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Job], int]:
        query = select(Job).order_by(Job.created_at.desc())
        count_query = select(func.count()).select_from(Job)

        if status:
            query = query.where(Job.status == status)
            count_query = count_query.where(Job.status == status)

        total = (await self.session.execute(count_query)).scalar_one()
        query = query.limit(page_size).offset((page - 1) * page_size)
        jobs = (await self.session.execute(query)).scalars().all()

        return list(jobs), total

    async def update_status(
        self,
        job_id: uuid.UUID,
        status: str,
        updated_at: datetime | None = None,
        **kwargs,
    ) -> None:
        job = await self.get_by_id(job_id)
        if job:
            job.status = status
            job.updated_at = updated_at or datetime.utcnow()
            for k, v in kwargs.items():
                setattr(job, k, v)
            await self.session.commit()
