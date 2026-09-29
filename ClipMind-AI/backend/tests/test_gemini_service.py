from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from app.services import gemini


def _api_error(error_type, code: int):
    return error_type(code, {"error": {"code": code, "message": "provider error"}})


def _configure_fast_retries(monkeypatch) -> list[float]:
    delays: list[float] = []
    monkeypatch.setattr(gemini.time, "sleep", delays.append)
    monkeypatch.setattr(gemini.random, "uniform", lambda _low, _high: 1.0)
    return delays


def _request(generate):
    return gemini.generate_content_with_retry(
        generate,
        operation="unit-test",
        model="test-model",
        request_timeout_seconds=0,
    )


def test_retries_503_then_returns_success(monkeypatch) -> None:
    delays = _configure_fast_retries(monkeypatch)
    attempts = 0
    response = SimpleNamespace(text='{"ok": true}')

    def generate():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _api_error(errors.ServerError, 503)
        return response

    assert _request(generate) is response
    assert attempts == 2
    assert delays == [1.0]


def test_repeated_503_raises_controlled_failure(monkeypatch) -> None:
    delays = _configure_fast_retries(monkeypatch)
    attempts = 0

    def generate():
        nonlocal attempts
        attempts += 1
        raise _api_error(errors.ServerError, 503)

    with pytest.raises(gemini.GeminiProviderUnavailableError) as caught:
        _request(generate)

    assert attempts == gemini.MAX_GEMINI_ATTEMPTS
    assert caught.value.status_code == 503
    assert caught.value.attempts == gemini.MAX_GEMINI_ATTEMPTS
    assert delays == [1.0, 2.0, 4.0]


def test_retries_429(monkeypatch) -> None:
    delays = _configure_fast_retries(monkeypatch)
    attempts = 0

    def generate():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _api_error(errors.ClientError, 429)
        return "success"

    assert _request(generate) == "success"
    assert attempts == 2
    assert delays == [1.0]


@pytest.mark.parametrize("code", [400, 401, 403])
def test_permanent_api_errors_are_not_retried(monkeypatch, code: int) -> None:
    delays = _configure_fast_retries(monkeypatch)
    error_type = errors.ServerError if code >= 500 else errors.ClientError
    attempts = 0

    def generate():
        nonlocal attempts
        attempts += 1
        raise _api_error(error_type, code)

    with pytest.raises(errors.APIError) as caught:
        _request(generate)

    assert caught.value.code == code
    assert attempts == 1
    assert delays == []


def test_timeout_is_retried(monkeypatch) -> None:
    delays = _configure_fast_retries(monkeypatch)
    attempts = 0

    def generate():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("request timed out")
        return "success"

    assert _request(generate) == "success"
    assert attempts == 2
    assert delays == [1.0]


def test_operation_deadline_stops_further_retries(monkeypatch) -> None:
    delays: list[float] = []
    elapsed = 0.0
    attempts = 0

    def monotonic() -> float:
        return elapsed

    def sleep(delay: float) -> None:
        nonlocal elapsed
        delays.append(delay)
        elapsed += delay

    def generate():
        nonlocal attempts, elapsed
        attempts += 1
        elapsed += 0.25 if attempts == 1 else 0.75
        raise _api_error(errors.ServerError, 503)

    monkeypatch.setattr(gemini, "GEMINI_OPERATION_TIMEOUT_SECONDS", 2.0)
    monkeypatch.setattr(gemini.time, "monotonic", monotonic)
    monkeypatch.setattr(gemini.time, "sleep", sleep)
    monkeypatch.setattr(gemini.random, "uniform", lambda _low, _high: 1.0)

    with pytest.raises(gemini.GeminiProviderUnavailableError) as caught:
        gemini.generate_content_with_retry(
            generate,
            operation="unit-test",
            model="test-model",
            request_timeout_seconds=0.75,
        )

    assert caught.value.reason == "operation_deadline"
    assert attempts == 2
    assert delays == [1.0]


def test_retry_after_is_respected_and_bounded(monkeypatch) -> None:
    delays = _configure_fast_retries(monkeypatch)
    attempts = 0
    response = httpx.Response(503, headers={"Retry-After": "30"})

    def generate():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise errors.ServerError(
                503,
                {"error": {"code": 503, "message": "provider error"}},
                response,
            )
        return "success"

    assert _request(generate) == "success"
    assert delays == [gemini.GEMINI_RETRY_AFTER_MAX_SECONDS]