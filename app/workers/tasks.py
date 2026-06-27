"""
Celery pipeline task: clean -> detect anomalies -> LLM classify -> LLM summarise.

Each step calls a dedicated service module. LLM steps use tenacity retry
(up to 3 attempts, exponential backoff). If ALL LLM retries fail, the job
is marked `llm_failed` instead of `failed` and processing continues.
"""

import logging
import os
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
from celery.utils.log import get_task_logger
from sqlalchemy import func

from app.core.config import settings
from app.core.database import get_sync_session
from app.domain.enums import JobStatus
from app.models.job import Job
from app.models.job_summary import JobSummary
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
    """Run the full 4-step pipeline for a given job UUID (passed as string)."""
    jid = uuid.UUID(job_id)
    logger.info("[%s] Pipeline started", job_id)

    # ── Set status to processing ──────────────────────────────────────────
    with get_sync_session() as session:
        job = session.get(Job, jid)
        if not job:
            logger.error("[%s] Job not found in DB; aborting", job_id)
            return
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.utcnow()

    try:
        # ── Load CSV ──────────────────────────────────────────────────────
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
            "[%s] Step 1/4 Cleaning done: %d→%d rows (%d dupes removed)",
            job_id, stats["total_rows"], stats["cleaned_rows"], stats["duplicate_rows"],
        )

        # ── Step 2: Anomaly detection ────────────────────────────────────
        from app.services.anomaly.detector import AnomalyDetector  # noqa: PLC0415

        detector = AnomalyDetector()
        annotated_df = detector.detect(cleaned_df)
        anomaly_count = int(annotated_df["is_anomaly"].sum())
        logger.info("[%s] Step 2/4 Anomaly detection done: %d anomalies", job_id, anomaly_count)

        # ── Persist cleaned + annotated transactions ──────────────────────
        with get_sync_session() as session:
            txns = [_row_to_transaction(row, jid) for _, row in annotated_df.iterrows()]
            session.bulk_save_objects(txns)

            job = session.get(Job, jid)
            job.total_rows = stats["total_rows"]
            job.cleaned_rows = stats["cleaned_rows"]
            job.duplicate_rows = stats["duplicate_rows"]
            job.anomaly_count = anomaly_count
            job.updated_at = datetime.utcnow()

        logger.info("[%s] Transactions saved to DB (%d rows)", job_id, len(txns))

        # ── Load DB UUIDs for LLM mapping ────────────────────────────────
        with get_sync_session() as session:
            txn_records = (
                session.query(Transaction)
                .filter(Transaction.job_id == jid)
                .all()
            )
            txn_data_for_llm = [
                {
                    "id": str(t.id),
                    "merchant": t.merchant or "",
                    "amount": float(t.amount or 0),
                    "currency": t.currency or "INR",
                    "category": t.category or "Uncategorised",
                }
                for t in txn_records
            ]

        # ── Step 3: LLM batch classification ────────────────────────────
        llm_failed = False
        from app.services.llm.provider import get_llm_provider  # noqa: PLC0415

        try:
            provider = get_llm_provider()
            id_to_category: dict[str, str] = provider.classify_batch(txn_data_for_llm)

            with get_sync_session() as session:
                for txn in session.query(Transaction).filter(Transaction.job_id == jid).all():
                    cat = id_to_category.get(str(txn.id))
                    if cat:
                        txn.llm_category = cat

            logger.info("[%s] Step 3/4 LLM classification done", job_id)

        except Exception as exc:
            logger.warning("[%s] Step 3/4 LLM classification failed after retries: %s", job_id, exc)
            llm_failed = True
            with get_sync_session() as session:
                session.query(Transaction).filter(Transaction.job_id == jid).update(
                    {"llm_failed": True}
                )

        # ── Step 4: LLM narrative summary ────────────────────────────────
        try:
            with get_sync_session() as session:
                txn_records = (
                    session.query(Transaction)
                    .filter(Transaction.job_id == jid)
                    .all()
                )
                txn_list_for_summary = [
                    {
                        "id": str(t.id),
                        "merchant": t.merchant,
                        "amount": float(t.amount or 0),
                        "currency": t.currency,
                        "category": t.llm_category or t.category,
                        "is_anomaly": t.is_anomaly,
                        "status": t.status,
                    }
                    for t in txn_records
                ]
                # Compute stats that don't need LLM
                total_spend = session.query(func.sum(Transaction.amount)).filter(
                    Transaction.job_id == jid
                ).scalar()
                db_anomaly_count = session.query(Transaction).filter(
                    Transaction.job_id == jid, Transaction.is_anomaly.is_(True)
                ).count()

            if not llm_failed:
                provider = get_llm_provider()
                summary_data = provider.generate_summary(txn_list_for_summary)

                with get_sync_session() as session:
                    existing = (
                        session.query(JobSummary)
                        .filter(JobSummary.job_id == jid)
                        .first()
                    )
                    if not existing:
                        session.add(
                            JobSummary(
                                id=uuid.uuid4(),
                                job_id=jid,
                                total_spend=summary_data.get("total_spend"),
                                top_merchants=summary_data.get("top_merchants"),
                                anomaly_count=summary_data.get("anomaly_count", db_anomaly_count),
                                category_breakdown=summary_data.get("category_breakdown"),
                                narrative=summary_data.get("narrative"),
                                risk_level=summary_data.get("risk_level"),
                                llm_failed=False,
                            )
                        )
                logger.info("[%s] Step 4/4 LLM summary done", job_id)

            else:
                # LLM was already marked failed; save computed stats only
                with get_sync_session() as session:
                    if not session.query(JobSummary).filter(JobSummary.job_id == jid).first():
                        session.add(
                            JobSummary(
                                id=uuid.uuid4(),
                                job_id=jid,
                                total_spend=total_spend,
                                anomaly_count=db_anomaly_count,
                                llm_failed=True,
                            )
                        )
                logger.info("[%s] Step 4/4 Skipped (LLM failed); computed-stats summary saved", job_id)

        except Exception as exc:
            logger.warning("[%s] Step 4/4 LLM summary failed after retries: %s", job_id, exc)
            llm_failed = True
            with get_sync_session() as session:
                if not session.query(JobSummary).filter(JobSummary.job_id == jid).first():
                    session.add(
                        JobSummary(
                            id=uuid.uuid4(),
                            job_id=jid,
                            total_spend=total_spend,
                            anomaly_count=db_anomaly_count,
                            llm_failed=True,
                        )
                    )

        # ── Finalise job status ───────────────────────────────────────────
        final_status = JobStatus.LLM_FAILED if llm_failed else JobStatus.COMPLETED
        with get_sync_session() as session:
            job = session.get(Job, jid)
            job.status = final_status
            job.updated_at = datetime.utcnow()

        logger.info("[%s] Pipeline complete. Final status: %s", job_id, final_status)

    except Exception as exc:
        logger.error("[%s] Pipeline failed with unhandled exception: %s", job_id, exc, exc_info=True)
        with get_sync_session() as session:
            job = session.get(Job, jid)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:1000]
                job.updated_at = datetime.utcnow()
        raise
