import os
import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_session
from app.repositories.job_repository import JobRepository
from app.repositories.transaction_repository import SummaryRepository, TransactionRepository
from app.schemas.job import (
    JobCreateResponse,
    JobListItem,
    JobListResponse,
    JobResultsResponse,
    JobStatusResponse,
    SummaryBrief,
)
from app.schemas.transaction import TransactionOut

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

    # Persist the job record first so we have the ID
    repo = JobRepository(session)
    job = await repo.create(original_filename=file.filename)

    # Save the CSV so the Celery worker can read it from the shared volume
    os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
    csv_path = os.path.join(settings.UPLOADS_DIR, f"{job.id}.csv")
    content = await file.read()
    with open(csv_path, "wb") as f:
        f.write(content)

    # Enqueue the processing pipeline (import here to avoid circular at module load)
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
    summary="Return current job status; includes LLM summary when completed",
)
async def get_job_status(job_id: uuid.UUID, session: SessionDep = None):
    repo = JobRepository(session)
    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    summary_brief: SummaryBrief | None = None
    if job.status in ("completed", "llm_failed"):
        summary_repo = SummaryRepository(session)
        db_summary = await summary_repo.get_by_job_id(job_id)
        if db_summary:
            summary_brief = SummaryBrief(
                total_spend=float(db_summary.total_spend) if db_summary.total_spend else None,
                anomaly_count=db_summary.anomaly_count,
                narrative=db_summary.narrative,
                risk_level=db_summary.risk_level,
                llm_failed=db_summary.llm_failed,
            )

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
        summary=summary_brief,
    )


# ---------------------------------------------------------------------------
# GET /{job_id}/results
# ---------------------------------------------------------------------------

@router.get(
    "/{job_id}/results",
    response_model=JobResultsResponse,
    summary="Full structured output: cleaned transactions, anomalies, and LLM summary",
)
async def get_job_results(job_id: uuid.UUID, session: SessionDep = None):
    repo = JobRepository(session)
    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if job.status not in ("completed", "llm_failed"):
        raise HTTPException(
            status_code=status.HTTP_425_TOO_EARLY,
            detail=f"Results not ready yet. Current status: {job.status}",
        )

    txn_repo = TransactionRepository(session)
    all_txns = await txn_repo.get_by_job_id(job_id)
    anomalies = [t for t in all_txns if t.is_anomaly]

    summary_repo = SummaryRepository(session)
    db_summary = await summary_repo.get_by_job_id(job_id)

    summary_dict: dict | None = None
    if db_summary:
        summary_dict = {
            "total_spend": float(db_summary.total_spend) if db_summary.total_spend else None,
            "top_merchants": db_summary.top_merchants,
            "anomaly_count": db_summary.anomaly_count,
            "category_breakdown": db_summary.category_breakdown,
            "narrative": db_summary.narrative,
            "risk_level": db_summary.risk_level,
            "llm_failed": db_summary.llm_failed,
        }

    return JobResultsResponse(
        job_id=job.id,
        status=job.status,
        transactions=[TransactionOut.model_validate(t) for t in all_txns],
        anomalies=[TransactionOut.model_validate(t) for t in anomalies],
        summary=summary_dict,
    )


# ---------------------------------------------------------------------------
# GET / (list jobs)
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=JobListResponse,
    summary="List all jobs with optional status filter and pagination",
)
async def list_jobs(
    session: SessionDep = None,
    status_filter: str | None = Query(None, alias="status", description="Filter by job status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    repo = JobRepository(session)
    jobs, total = await repo.list_jobs(status=status_filter, page=page, page_size=page_size)

    return JobListResponse(
        jobs=[
            JobListItem(
                job_id=j.id,
                status=j.status,
                original_filename=j.original_filename,
                total_rows=j.total_rows,
                cleaned_rows=j.cleaned_rows,
                anomaly_count=j.anomaly_count,
                created_at=j.created_at,
                updated_at=j.updated_at,
            )
            for j in jobs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
