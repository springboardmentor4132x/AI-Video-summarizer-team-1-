"""Run one safe, minimal request against the configured Gemini model."""

import logging
import socket
from importlib.metadata import version

import httpx
from google import genai
from google.genai import errors, types

from app.config import settings


def _safe_message(message: str | None, api_key: str) -> str:
    if not message:
        return "No provider message was supplied."
    return message.replace(api_key, "[REDACTED]") if api_key else message


def _classification(code: int, status: str, message: str) -> str:
    lowered = f"{status} {message}".lower()
    if code in (401, 403) or status in {"UNAUTHENTICATED", "PERMISSION_DENIED"}:
        return "Authentication/authorization failure."
    if code == 404 or status == "NOT_FOUND":
        return "Model or endpoint not found."
    if code == 429:
        return "HTTP 429 quota/rate-limit response."
    if code in (500, 502, 503, 504):
        if "model" in lowered or "capacity" in lowered or "high demand" in lowered:
            return f"HTTP {code} transient provider/model availability error."
        return f"HTTP {code} transient provider error."
    if any(term in lowered for term in ("schema", "structured output", "response_schema", "json schema")):
        return f"HTTP {code} schema/structured-output error."
    if code == 400:
        return "HTTP 400 request error; this probe sent no structured schema."
    return f"Gemini API error (HTTP {code})."


def main() -> None:
    logging.getLogger("google_genai").setLevel(logging.ERROR)
    api_key = (settings.gemini_api_key or "").strip()
    model = (settings.gemini_model or "gemini-2.5-flash").strip() or "gemini-2.5-flash"

    print(f"Gemini model: {model}")
    print(f"API key configured: {'YES' if api_key else 'NO'}")
    print(f"google-genai version: {version('google-genai')}")

    if not api_key:
        print("Request succeeded: NO")
        print("HTTP/status code: unavailable")
        print("Gemini exception class: Not attempted")
        print("Safe provider error message: Request not sent; API key is not configured.")
        print("Classification: Authentication/configuration failure.")
        return

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=20_000),
        )
        response = client.models.generate_content(
            model=model,
            contents="Reply only with OK.",
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=8),
        )
        succeeded = bool((getattr(response, "text", None) or "").strip())
        print(f"Request succeeded: {'YES' if succeeded else 'NO'}")
        print("HTTP/status code: 200" if succeeded else "HTTP/status code: unavailable")
        if not succeeded:
            print("Gemini exception class: None")
            print("Safe provider error message: Gemini returned no text content.")
            print("Classification: Empty response; no schema was sent.")
    except errors.APIError as exc:
        status = (exc.status or "").upper()
        message = _safe_message(exc.message, api_key)
        print("Request succeeded: NO")
        print(f"HTTP/status code: {exc.code}")
        print(f"Gemini exception class: {type(exc).__name__}")
        print(f"Safe provider error message: {message}")
        print(f"Classification: {_classification(exc.code, status, message)}")
        print("Schema-related: NO (the probe sent no structured-output schema).")
    except (httpx.HTTPError, socket.gaierror, TimeoutError, ConnectionError, OSError) as exc:
        print("Request succeeded: NO")
        print("HTTP/status code: unavailable")
        print(f"Gemini exception class: {type(exc).__name__}")
        print("Safe provider error message: No provider response; the request failed at the network/transport layer.")
        print("Classification: Network/timeout error.")
    except Exception as exc:
        safe_text = _safe_message(str(exc), api_key)
        print("Request succeeded: NO")
        print("HTTP/status code: unavailable")
        print(f"Gemini exception class: {type(exc).__name__}")
        print(f"Safe provider error message: {safe_text}")
        print("Classification: Local SDK/request setup error.")


if __name__ == "__main__":
    main()