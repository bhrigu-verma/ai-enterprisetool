"""Resilience utilities — retry with exponential backoff and jitter.

Designed for wrapping external API calls (GitHub, Slack, Anthropic) so
that transient failures don't crash the pipeline.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Exceptions that are always worth retrying
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class RetryExhausted(Exception):
    """All retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_exception: Exception) -> None:
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(
            f"Failed after {attempts} attempts. Last error: {last_exception}"
        )


def retry_async(
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator that retries an async function with exponential backoff.

    Parameters
    ----------
    max_attempts:
        Total number of attempts (including the first).
    base_delay:
        Initial delay in seconds between retries.
    max_delay:
        Maximum delay in seconds (caps exponential growth).
    jitter:
        Add random jitter to avoid thundering-herd.
    retryable_exceptions:
        Tuple of exception types that trigger a retry.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    if jitter:
                        delay *= 0.5 + random.random()  # noqa: S311
                    logger.warning(
                        "Retry %d/%d for %s after %.1fs — %s: %s",
                        attempt,
                        max_attempts,
                        func.__qualname__,
                        delay,
                        type(exc).__name__,
                        exc,
                    )
                    await asyncio.sleep(delay)
            raise RetryExhausted(max_attempts, last_exc)  # type: ignore[arg-type]

        return wrapper

    return decorator


def is_retryable_http_status(status_code: int) -> bool:
    """Return True if the HTTP status code represents a transient error."""
    return status_code in _TRANSIENT_STATUS_CODES
