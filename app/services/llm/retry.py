"""
Retry decorator for LLM calls using tenacity.

Configuration:
  - Exponential backoff (2s, 4s, 8s, capped at 60s)
  - 4 total attempts (1 initial + 3 retries)
  - Re-raises exception on final failure for caller to handle

Usage:
    @llm_retry
    def my_llm_call(self, ...):
        ...
"""

import logging
from functools import wraps
from typing import Callable, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)

_RETRY_DECORATOR = retry(
    stop=stop_after_attempt(4),          # 1 initial + 3 retries = 4 total attempts
    wait=wait_exponential(
        multiplier=2, min=2, max=60      # 2s → 4s → 8s … capped at 60s
    ),
    retry=retry_if_exception_type(Exception),
    reraise=True,                        # re-raise original exception after all retries exhausted
    before_sleep=lambda rs: logger.warning(
        "LLM call attempt %d/4 failed; retrying with exponential backoff …",
        rs.attempt_number,
    ),
)


def llm_retry(func: F) -> F:
    """Wrap a method with tenacity exponential-backoff retry (3 attempts)."""
    wrapped = _RETRY_DECORATOR(func)

    @wraps(func)
    def inner(*args, **kwargs):
        return wrapped(*args, **kwargs)

    return inner  # type: ignore[return-value]
