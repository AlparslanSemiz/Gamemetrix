"""Shared contracts and safe error normalization for text-generation providers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Protocol

import httpx


ResponseValidator = Callable[[str], bool]


class ErrorCategory(StrEnum):
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    NETWORK = "network"
    SERVER = "server"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    INVALID_MODEL = "invalid_model"
    INVALID_REQUEST = "invalid_request"
    INVALID_RESPONSE = "invalid_response"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NOT_CONFIGURED = "not_configured"
    INTERNAL = "internal"


@dataclass(frozen=True)
class GenerationRequest:
    system_prompt: str
    user_prompt: str
    max_output_tokens: int
    temperature: float
    json_object: bool = False
    response_validator: ResponseValidator | None = None


@dataclass(frozen=True)
class GenerationResult:
    text: str
    provider: str
    model: str
    total_tokens: int = 0


class ProviderFailure(Exception):
    """Sanitized provider failure; raw response bodies never cross this boundary."""

    def __init__(
        self,
        category: ErrorCategory,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        fallback_allowed: bool = True,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(category.value)
        self.category = category
        self.status_code = status_code
        self.retryable = retryable
        self.fallback_allowed = fallback_allowed
        self.retry_after = retry_after


class AIProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    def is_configured(self) -> bool: ...

    async def generate(
        self,
        request: GenerationRequest,
        timeout_seconds: float,
    ) -> GenerationResult: ...

    def classify_error(
        self,
        status_code: int,
        payload: object | None,
        headers: httpx.Headers,
    ) -> ProviderFailure: ...


def classify_http_error(
    status_code: int,
    payload: object | None,
    headers: httpx.Headers,
) -> ProviderFailure:
    """Map common HTTP/provider errors without retaining sensitive messages."""
    retry_after = retry_after_seconds(headers)
    if status_code == 408:
        return ProviderFailure(
            ErrorCategory.TIMEOUT,
            status_code=status_code,
            retryable=True,
            retry_after=retry_after,
        )
    if status_code == 429:
        return ProviderFailure(
            ErrorCategory.RATE_LIMITED,
            status_code=status_code,
            retryable=True,
            retry_after=retry_after,
        )
    if status_code >= 500:
        return ProviderFailure(
            ErrorCategory.SERVER,
            status_code=status_code,
            retryable=True,
            retry_after=retry_after,
        )
    if status_code == 401:
        return ProviderFailure(ErrorCategory.AUTHENTICATION, status_code=status_code)
    if status_code == 403:
        return ProviderFailure(ErrorCategory.PERMISSION, status_code=status_code)
    if status_code == 404 or _looks_like_model_error(payload):
        return ProviderFailure(ErrorCategory.INVALID_MODEL, status_code=status_code)
    return ProviderFailure(
        ErrorCategory.INVALID_REQUEST,
        status_code=status_code,
        fallback_allowed=False,
    )


def transport_failure(exc: httpx.HTTPError) -> ProviderFailure:
    if isinstance(exc, httpx.TimeoutException):
        return ProviderFailure(ErrorCategory.TIMEOUT, retryable=True)
    return ProviderFailure(ErrorCategory.NETWORK, retryable=True)


def retry_after_seconds(headers: httpx.Headers) -> float | None:
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw.strip()))
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0.0, (parsed - datetime.now(UTC)).total_seconds())


def extract_openai_text(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    if isinstance(payload.get("error"), dict):
        status = _nested_int(payload, "error", "code")
        if status is not None:
            raise classify_http_error(status, payload, httpx.Headers())
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    first = choices[0]
    if not isinstance(first, dict):
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    if first.get("finish_reason") == "error" or isinstance(first.get("error"), dict):
        status = _nested_int(first, "error", "code")
        if status is not None:
            raise classify_http_error(status, first, httpx.Headers())
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    message = first.get("message")
    if not isinstance(message, dict):
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    return content.strip()


def openai_total_tokens(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return 0
    total = usage.get("total_tokens")
    return total if isinstance(total, int) and total >= 0 else 0


def _nested_int(payload: dict[str, object], key: str, child: str) -> int | None:
    nested = payload.get(key)
    if not isinstance(nested, dict):
        return None
    value = nested.get(child)
    return value if isinstance(value, int) else None


def _looks_like_model_error(payload: object | None) -> bool:
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    values = (
        error.get("code"),
        error.get("type"),
        error.get("status"),
        error.get("message"),
    )
    return any("model" in str(value).casefold() for value in values if value is not None)
