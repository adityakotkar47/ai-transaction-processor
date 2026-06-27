"""Celery pipeline task: clean raw CSV, detect anomalies, persist transactions."""

import logging
import os
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
from celery.utils.log import get_task_logger

from app.core.config import settings
from app.core.database import get_sync_session
from app.domain.enums import JobStatus
from app.models.job import Job
from app.models.transaction import Transaction
from app.workers.celery_app import celery_app

logger: logging.Logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# Helper: convert cleaned pandas row into a Transaction ORM object
# ---------------------------------------------------------------------------

def _row_to_transaction(row: pd.Series, job_id: uuid.UUID) -> Transaction:
    raw_date = row.get("txn_date")
    parsed_date: date | None = None
    if raw_date and pd.notna(raw_date):
        try:
            parsed_date = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
        except ValueError:
            parsed_date = None

    raw_amount = row.get("amount")
    parsed_amount: Decimal | None = None
    if raw_amount is not None and pd.notna(raw_amount):
        try:
            parsed_amount = Decimal(str(raw_amount))
        except InvalidOperation:
            parsed_amount = None

    return Transaction(
        id=uuid.uuid4(),
        job_id=job_id,
        txn_id=str(row.get("txn_id", "")).strip() or None,
        txn_date=parsed_date,
        merchant=str(row.get("merchant", "")).strip() or None,
        amount=parsed_amount,
        currency=str(row.get("currency", "")).strip() or None,
        status=str(row.get("status", "")).strip() or None,
        category=str(row.get("category", "")).strip() or None,
        account_id=str(row.get("account_id", "")).strip() or None,
        notes=str(row.get("notes", "")).strip() or None,
        is_anomaly=bool(row.get("is_anomaly", False)),
        anomaly_reason=str(row.get("anomaly_reason", "")).strip() or None,
    )


# ---------------------------------------------------------------------------
# Main pipeline task
# ---------------------------------------------------------------------------

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

        # ── Step 1: Clean ─────────────────────────────────────────────────
        from app.services.cleaning.cleaner import TransactionCleaner  # noqa: PLC0415

        cleaner = TransactionCleaner()
        cleaned_df, stats = cleaner.clean(raw_df)
        logger.info(
            "[%s] Step 1/2 Cleaning done: %d->%d rows (%d dupes removed)",
            job_id, stats["total_rows"], stats["cleaned_rows"], stats["duplicate_rows"],
        )

        # ── Step 2: Anomaly detection ────────────────────────────────────
        from app.services.anomaly.detector import AnomalyDetector  # noqa: PLC0415

        detector = AnomalyDetector()
        annotated_df = detector.detect(cleaned_df)
        anomaly_count = int(annotated_df["is_anomaly"].sum())
        logger.info("[%s] Step 2/2 Anomaly detection done: %d anomalies", job_id, anomaly_count)

        with get_sync_session() as session:
            txns = [_row_to_transaction(row, jid) for _, row in annotated_df.iterrows()]
            session.bulk_save_objects(txns)

            job = session.get(Job, jid)
            job.total_rows = stats["total_rows"]
            job.cleaned_rows = stats["cleaned_rows"]
            job.duplicate_rows = stats["duplicate_rows"]
            job.anomaly_count = anomaly_count
            job.status = JobStatus.COMPLETED
            job.updated_at = datetime.utcnow()

        logger.info("[%s] Pipeline complete. %d transactions saved.", job_id, len(txns))

    except Exception as exc:
        logger.error("[%s] Pipeline failed: %s", job_id, exc, exc_info=True)
        with get_sync_session() as session:
            job = session.get(Job, jid)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:1000]
                job.updated_at = datetime.utcnow()
        raise
