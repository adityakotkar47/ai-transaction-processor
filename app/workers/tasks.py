"""Celery pipeline task."""

import logging
import os
import uuid
from datetime import datetime

import pandas as pd
from celery.utils.log import get_task_logger

from app.core.config import settings
from app.core.database import get_sync_session
from app.domain.enums import JobStatus
from app.models.job import Job
from app.workers.celery_app import celery_app

logger: logging.Logger = get_task_logger(__name__)


@celery_app.task(bind=True, name="app.workers.tasks.process_job")
def process_job(self, job_id: str) -> None:
    """Run the processing pipeline for a given job UUID (passed as string)."""
    jid = uuid.UUID(job_id)
    logger.info("[%s] Pipeline started", job_id)

    with get_sync_session() as session:
        job = session.get(Job, jid)
        if not job:
            logger.error("[%s] Job not found in DB; aborting", job_id)
            return
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.utcnow()

    try:
        csv_path = os.path.join(settings.UPLOADS_DIR, f"{job_id}.csv")
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV not found at {csv_path}")

        raw_df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        logger.info("[%s] Loaded %d raw rows", job_id, len(raw_df))

        # Cleaning and processing will be wired in subsequent steps
        with get_sync_session() as session:
            job = session.get(Job, jid)
            job.total_rows = len(raw_df)
            job.status = JobStatus.COMPLETED
            job.updated_at = datetime.utcnow()

        logger.info("[%s] Pipeline complete", job_id)

    except Exception as exc:
        logger.error("[%s] Pipeline failed: %s", job_id, exc, exc_info=True)
        with get_sync_session() as session:
            job = session.get(Job, jid)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:1000]
                job.updated_at = datetime.utcnow()
        raise
