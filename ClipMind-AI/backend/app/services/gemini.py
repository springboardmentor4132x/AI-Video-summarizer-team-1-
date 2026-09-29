"""Shared transient-error handling for Gemini content generation."""

import logging
import random
import socket
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar

import httpx
from google.genai import errors, types

logger = logging.getLogger(__name__)

TRANSIENT_GEMINI_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_GEMINI_ATTEMPTS = 4
GEMINI_RETRY_BASE_DELAY_SECONDS = 1.0
GEMINI_RETRY_MAX_DELAY_SECONDS = 4.0
GEMINI_RETRY_AFTER_MAX_SECONDS = 10.0
GEMINI_OPERATION_TIMEOUT_SECONDS = 155.0
GEMINI_REQUEST_TIMEOUT_SECONDS = 30.0
GEMINI_SHORT_REQUEST_TIMEOUT_SECONDS = 20.0
GEMINI_RETRY_JITTER_RATIO = 0.2

_Result = TypeVar("_Result")


class GeminiProviderUnavailableError(Exception):
    """Raised when Gemini remains unavailable after bounded retries."""

    def __init__(self, status_code: int | None, attempts: int, reason: str) -> None:
        self.status_code = status_code
        self.attempts = attempts
        self.reason = reason
        super().__init__("Gemini is temporarily unavailable. Please try again shortly.")


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, errors.APIError):
        return exc.code in TRANSIENT_GEMINI_STATUS_CODES
    return isinstance(
        exc,
        (httpx.TransportError, TimeoutError, ConnectionError, socket.gaierror),
    )


def _status_code(exc: Exception) -> int | None:
    if isinstance(exc, errors.APIError):
        return exc.code
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None

    retry_after = headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        seconds = float(retry_after)
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(retry_after)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    if seconds <= 0:
        return None
    return min(seconds, GEMINI_RETRY_AFTER_MAX_SECONDS)


def _retry_delay(attempt: int, exc: Exception) -> float:
    backoff = min(
        GEMINI_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
        GEMINI_RETRY_MAX_DELAY_SECONDS,
    )
    jittered_backoff = backoff * random.uniform(
        1 - GEMINI_RETRY_JITTER_RATIO,
        1 + GEMINI_RETRY_JITTER_RATIO,
    )
    return max(jittered_backoff, _retry_after_seconds(exc) or 0.0)


def gemini_http_options(request_timeout_seconds: float) -> types.HttpOptions:
    """Set a finite request timeout and disable SDK retries owned by our helper."""
    return types.HttpOptions(
        timeout=int(request_timeout_seconds * 1000),
        retry_options=types.HttpRetryOptions(attempts=1),
    )


def _log_failure(
    *,
    operation: str,
    model: str,
    attempt: int,
    exc: Exception,
    retry: bool,
    reason: str,
    delay: float | None = None,
) -> None:
    logger.warning(
        "Gemini request failed operation=%s model=%s attempt=%s/%s status_code=%s "
        "provider_status=%s exception_type=%s retry=%s reason=%s delay_seconds=%s",
        operation,
        model,
        attempt,
        MAX_GEMINI_ATTEMPTS,
        _status_code(exc),
        getattr(exc, "status", None),
        type(exc).__name__,
        retry,
        reason,
        round(delay, 2) if delay is not None else None,
    )


def generate_content_with_retry(
    generate: Callable[[], _Result],
    *,
    operation: str,
    model: str,
    request_timeout_seconds: float = GEMINI_REQUEST_TIMEOUT_SECONDS,
) -> _Result:
    """Retry only transient Gemini failures within a bounded operation deadline."""
    deadline = time.monotonic() + GEMINI_OPERATION_TIMEOUT_SECONDS
    last_error: Exception | None = None

    for attempt in range(1, MAX_GEMINI_ATTEMPTS + 1):
        remaining = deadline - time.monotonic()
        if remaining < request_timeout_seconds:
            if last_error is None:
                raise GeminiProviderUnavailableError(None, 0, "operation_deadline")
            _log_failure(
                operation=operation,
                model=model,
                attempt=attempt - 1,
                exc=last_error,
                retry=False,
                reason="operation_deadline",
            )
            raise GeminiProviderUnavailableError(
                _status_code(last_error), attempt - 1, "operation_deadline"
            ) from last_error

        try:
            return generate()
        except Exception as exc:
            if not _is_transient_error(exc):
                _log_failure(
                    operation=operation,
                    model=model,
                    attempt=attempt,
                    exc=exc,
                    retry=False,
                    reason="permanent_or_unclassified_error",
                )
                raise

            last_error = exc
            if attempt == MAX_GEMINI_ATTEMPTS:
                _log_failure(
                    operation=operation,
                    model=model,
                    attempt=attempt,
                    exc=exc,
                    retry=False,
                    reason="max_attempts_exhausted",
                )
                raise GeminiProviderUnavailableError(
                    _status_code(exc), attempt, "max_attempts_exhausted"
                ) from exc

            delay = _retry_delay(attempt, exc)
            remaining = deadline - time.monotonic()
            if remaining < delay + request_timeout_seconds:
                _log_failure(
                    operation=operation,
                    model=model,
                    attempt=attempt,
                    exc=exc,
                    retry=False,
                    reason="operation_deadline",
                )
                raise GeminiProviderUnavailableError(
                    _status_code(exc), attempt, "operation_deadline"
                ) from exc

            _log_failure(
                operation=operation,
                model=model,
                attempt=attempt,
                exc=exc,
                retry=True,
                reason="transient_provider_or_transport_error",
                delay=delay,
            )
            time.sleep(delay)

    raise RuntimeError("Gemini retry loop exited without a result.")