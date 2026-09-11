"""One safe public-error contract for the agent and its voice providers."""

from dataclasses import dataclass
from typing import Literal

import httpx
from fastapi import HTTPException
from loguru import logger

Provider = Literal["daily", "elevenlabs", "openrouter", "transport", "unknown"]


@dataclass(frozen=True)
class PublicError:
    code: str
    message: str
    status_code: int
    retryable: bool = False

    def detail(self) -> dict[str, str | bool]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}

    def as_http_exception(self) -> HTTPException:
        return HTTPException(status_code=self.status_code, detail=self.detail())


VOICE_NOT_CONFIGURED = PublicError(
    "voice_not_configured", "Voice is not configured on this server.", 503
)
VOICE_ALREADY_ACTIVE = PublicError(
    "voice_already_active", "You already have an active conversation.", 409
)
VOICE_ENDED = PublicError("voice_ended", "This call has ended. Start a new conversation.", 409)
VOICE_SESSION_NOT_FOUND = PublicError("voice_session_not_found", "Session not found.", 404)
VOICE_CAPACITY = PublicError(
    "voice_capacity_reached", "All voice sessions are busy. Try again shortly.", 429, True
)
VOICE_INVALID_REQUEST = PublicError("invalid_request", "The request is invalid.", 422)
SERVICE_UNAUTHORIZED = PublicError("service_unauthorized", "Unauthorized service request.", 401)
USER_CONTEXT_REQUIRED = PublicError(
    "user_context_required", "Authenticated user context is required.", 400
)


def _provider_name(*hints: object) -> Provider:
    value = " ".join(str(hint or "").lower() for hint in hints)
    if "daily" in value:
        return "daily"
    if "eleven" in value or "scribe" in value:
        return "elevenlabs"
    if "openrouter" in value or "gpt" in value or "llm" in value:
        return "openrouter"
    if "transport" in value or "websocket" in value:
        return "transport"
    return "unknown"


def classify_voice_error(
    error: BaseException | None = None,
    *,
    source: object | None = None,
    description: object | None = None,
) -> PublicError:
    """Classify an upstream failure without returning or logging its payload."""
    provider = _provider_name(source, type(error).__name__ if error else "", description)
    status = None
    if isinstance(error, httpx.HTTPError) and getattr(error, "response", None) is not None:
        status = error.response.status_code

    if status in (401, 403):
        suffix, message, http_status, retryable = (
            "authentication_failed",
            "A voice service is unavailable. Please try again later.",
            503,
            False,
        )
    elif status == 429:
        suffix, message, http_status, retryable = (
            "rate_limited",
            "A voice service is busy. Try again shortly.",
            429,
            True,
        )
    elif status in (408, 504) or isinstance(error, (httpx.TimeoutException, TimeoutError)):
        suffix, message, http_status, retryable = (
            "timeout",
            "A voice service took too long. Start a new call.",
            504,
            True,
        )
    elif status is not None and 400 <= status < 500:
        suffix, message, http_status, retryable = (
            "request_rejected",
            "A voice service could not accept this call. Start a new call.",
            502,
            False,
        )
    elif status is not None or isinstance(error, httpx.HTTPError):
        suffix, message, http_status, retryable = (
            "unavailable",
            "A voice service is temporarily unavailable. Start a new call.",
            503,
            True,
        )
    else:
        suffix, message, http_status, retryable = (
            "failed",
            "The voice connection stopped unexpectedly. Start a new call.",
            502,
            True,
        )
    return PublicError(f"voice_{provider}_{suffix}", message, http_status, retryable)


def log_voice_error(public: PublicError, error: BaseException | None = None) -> None:
    """Keep diagnostics useful without writing audio, transcripts, keys or provider bodies."""
    logger.warning(
        "voice_failure code={} retryable={} exception_type={}",
        public.code,
        public.retryable,
        type(error).__name__ if error else "none",
    )
