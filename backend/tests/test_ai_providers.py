from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from types import SimpleNamespace

import httpx
import pytest

from app.integrations import cloudflare_ai, gemini, openrouter
from app.integrations.ai_types import (
    ErrorCategory,
    GenerationRequest,
    ProviderFailure,
    retry_after_seconds,
)


class _Client:
    def __init__(
        self,
        response: httpx.Response,
        calls: list[dict[str, object]],
    ) -> None:
        self.response = response
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url: str, **kwargs) -> httpx.Response:
        self.calls.append({"url": url, **kwargs})
        return self.response


def _request(*, json_object: bool = False) -> GenerationRequest:
    return GenerationRequest(
        system_prompt="Return only the requested value.",
        user_prompt="Classify this catalog row.",
        max_output_tokens=220,
        temperature=0.2,
        json_object=json_object,
    )


@pytest.mark.asyncio
async def test_gemini_builds_generate_content_request_and_normalizes_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    response = httpx.Response(
        200,
        json={
            "candidates": [{"content": {"parts": [{"text": '{"verdict":"OK"}'}]}}],
            "usageMetadata": {"totalTokenCount": 41},
        },
        request=httpx.Request("POST", "https://example.test"),
    )
    settings = SimpleNamespace(
        GEMINI_API_KEY="gemini-secret",
        GEMINI_MODEL="gemini-2.5-flash-lite",
        GEMINI_MIN_REQUEST_INTERVAL_SECONDS=0.0,
        gemini_configured=lambda: True,
    )
    monkeypatch.setattr(gemini, "get_settings", lambda: settings)
    monkeypatch.setattr(
        gemini.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(response, calls),
    )
    monkeypatch.setattr(gemini, "_last_request_started", 0.0)

    result = await gemini.GeminiProvider().generate(_request(json_object=True), 10)

    assert result.text == '{"verdict":"OK"}'
    assert result.total_tokens == 41
    assert calls[0]["url"].endswith("/gemini-2.5-flash-lite:generateContent")
    assert calls[0]["headers"]["x-goog-api-key"] == "gemini-secret"
    generation = calls[0]["json"]["generationConfig"]
    assert generation["maxOutputTokens"] == 220
    assert generation["responseMimeType"] == "application/json"
    assert generation["thinkingConfig"] == {"thinkingBudget": 0}


@pytest.mark.asyncio
async def test_cloudflare_uses_openai_compatible_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    response = httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "normalized"}}],
            "usage": {"total_tokens": 17},
        },
        request=httpx.Request("POST", "https://example.test"),
    )
    settings = SimpleNamespace(
        CLOUDFLARE_API_TOKEN="cloudflare-secret",
        CLOUDFLARE_ACCOUNT_ID="a" * 32,
        CLOUDFLARE_MODEL="@cf/openai/gpt-oss-20b",
        cloudflare_ai_configured=lambda: True,
    )
    monkeypatch.setattr(cloudflare_ai, "get_settings", lambda: settings)
    monkeypatch.setattr(
        cloudflare_ai.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(response, calls),
    )

    result = await cloudflare_ai.CloudflareAIProvider().generate(_request(), 10)

    assert result.text == "normalized"
    assert result.total_tokens == 17
    assert calls[0]["url"] == (
        f"https://api.cloudflare.com/client/v4/accounts/{'a' * 32}"
        "/ai/v1/chat/completions"
    )
    assert calls[0]["json"]["model"] == "@cf/openai/gpt-oss-20b"
    assert calls[0]["headers"]["Authorization"] == "Bearer cloudflare-secret"


@pytest.mark.asyncio
async def test_openrouter_normalizes_success_and_rejects_error_inside_http_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        OPENROUTER_API_KEY="openrouter-secret",
        OPENROUTER_MODEL="openrouter/free",
        openrouter_configured=lambda: True,
    )
    monkeypatch.setattr(openrouter, "get_settings", lambda: settings)
    calls: list[dict[str, object]] = []
    success = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "free answer"}}]},
        request=httpx.Request("POST", "https://example.test"),
    )
    monkeypatch.setattr(
        openrouter.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(success, calls),
    )

    result = await openrouter.OpenRouterProvider().generate(_request(), 10)

    assert result.text == "free answer"
    assert calls[0]["json"]["model"] == "openrouter/free"

    error = httpx.Response(
        200,
        json={
            "error": {
                "code": 429,
                "message": "do not log this provider message",
                "metadata": {"error_type": "rate_limit_exceeded"},
            }
        },
        request=httpx.Request("POST", "https://example.test"),
    )
    monkeypatch.setattr(
        openrouter.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(error, []),
    )

    with pytest.raises(ProviderFailure) as exc_info:
        await openrouter.OpenRouterProvider().generate(_request(), 10)

    assert exc_info.value.category == ErrorCategory.RATE_LIMITED
    assert exc_info.value.retryable is True


def test_permanent_provider_errors_are_not_retryable() -> None:
    provider = openrouter.OpenRouterProvider()

    auth = provider.classify_error(401, {}, httpx.Headers())
    invalid = provider.classify_error(400, {}, httpx.Headers())
    model = provider.classify_error(
        400,
        {"error": {"message": "invalid model identifier"}},
        httpx.Headers(),
    )

    assert auth.category == ErrorCategory.AUTHENTICATION
    assert auth.retryable is False
    assert invalid.category == ErrorCategory.INVALID_REQUEST
    assert invalid.retryable is False
    assert invalid.fallback_allowed is False
    assert model.category == ErrorCategory.INVALID_MODEL
    assert model.fallback_allowed is True


def test_retry_after_supports_http_date() -> None:
    future = datetime.now(UTC) + timedelta(seconds=3)

    delay = retry_after_seconds(httpx.Headers({"Retry-After": format_datetime(future)}))

    assert delay is not None
    assert 0 < delay <= 3
