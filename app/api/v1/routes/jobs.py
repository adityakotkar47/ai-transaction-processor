import os
import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_session
from app.repositories.job_repository import JobRepository
from app.schemas.job import JobCreateResponse, JobStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a CSV file and enqueue the processing pipeline",
)
async def upload_csv(
    file: UploadFile = File(...),
    session: SessionDep = None,
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv files are accepted.",
        )

    repo = JobRepository(session)
    job = await repo.create(original_filename=file.filename)

    os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
    csv_path = os.path.join(settings.UPLOADS_DIR, f"{job.id}.csv")
    content = await file.read()
    with open(csv_path, "wb") as f:
        f.write(content)

    from app.workers.tasks import process_job  # noqa: PLC0415

    process_job.delay(str(job.id))

    logger.info("Job %s enqueued for file %s", job.id, file.filename)
    return JobCreateResponse(
        job_id=job.id,
        status="pending",
        message="Job enqueued successfully. Poll /status for updates.",
    )


# ---------------------------------------------------------------------------
# GET /{job_id}/status
# ---------------------------------------------------------------------------

@router.get(
    "/{job_id}/status",
    response_model=JobStatusResponse,
    summary="Return current job status",
)
async def get_job_status(job_id: uuid.UUID, session: SessionDep = None):
    repo = JobRepository(session)
    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        original_filename=job.original_filename,
        total_rows=job.total_rows,
        cleaned_rows=job.cleaned_rows,
        duplicate_rows=job.duplicate_rows,
        anomaly_count=job.anomaly_count,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
