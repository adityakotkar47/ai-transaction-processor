import logging
import sys
from app.core.config import settings


def setup_logging() -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    # Quiet noisy third-party loggers
    for noisy in ("sqlalchemy.engine", "celery.app.trace", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
