from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "transaction_processor",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Observability
    task_track_started=True,
    worker_send_task_events=True,
    task_send_sent_event=True,
    # Timeouts (generous for LLM calls + large CSVs)
    task_soft_time_limit=600,   # 10 min soft — raises SoftTimeLimitExceeded
    task_time_limit=720,        # 12 min hard — kills worker process
    # Reliability
    broker_connection_retry_on_startup=True,
    task_acks_late=True,        # Re-queue if worker dies mid-task
    task_reject_on_worker_lost=True,
)
