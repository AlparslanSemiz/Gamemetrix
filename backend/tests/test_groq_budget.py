from types import SimpleNamespace

import httpx
import pytest

from app.integrations import groq
from app.services import summarizer


class _Limiter:
    def __init__(self, allowed: bool = True):
        self.allowed = allowed
        self.sources: list[str] = []

    async def acquire(self, source: str) -> bool:
        self.sources.append(source)
        return self.allowed


class _Client:
    def __init__(self, calls: list[dict[str, object]]):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url: str, **kwargs) -> httpx.Response:
        self.calls.append({"url": url, **kwargs})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"verdict":"OK"}'}}]},
            request=httpx.Request("POST", url),
        )


@pytest.mark.asyncio
async def test_groq_uses_the_shared_budget_and_json_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    limiter = _Limiter()
    settings = SimpleNamespace(
        GROQ_API_KEY="test-key",
        GROQ_MODEL="openai/gpt-oss-20b",
        GROQ_MIN_REQUEST_INTERVAL_SECONDS=12.0,
        groq_configured=lambda: True,
    )
    monkeypatch.setattr(groq, "get_settings", lambda: settings)
    monkeypatch.setattr(groq, "get_rate_limiter", lambda: limiter)
    monkeypatch.setattr(groq.httpx, "AsyncClient", lambda **_kwargs: _Client(calls))
    monkeypatch.setattr(groq, "_last_request_started", 0.0)

    result = await groq.generate_text(
        "Return JSON.",
        "Review this row.",
        json_object=True,
    )

    assert result == '{"verdict":"OK"}'
    assert limiter.sources == ["Groq"]
    assert calls[0]["json"]["model"] == "openai/gpt-oss-20b"
    assert calls[0]["json"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_groq_stops_before_http_when_daily_budget_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = _Limiter(allowed=False)
    settings = SimpleNamespace(
        GROQ_API_KEY="test-key",
        GROQ_MODEL="openai/gpt-oss-20b",
        GROQ_MIN_REQUEST_INTERVAL_SECONDS=12.0,
        groq_configured=lambda: True,
    )
    monkeypatch.setattr(groq, "get_settings", lambda: settings)
    monkeypatch.setattr(groq, "get_rate_limiter", lambda: limiter)
    monkeypatch.setattr(
        groq.httpx,
        "AsyncClient",
        lambda **_kwargs: pytest.fail("HTTP must not run after budget exhaustion"),
    )

    assert await groq.generate_text("system", "user") is None
    assert limiter.sources == ["Groq"]


@pytest.mark.asyncio
async def test_summary_generation_bounds_provider_text_before_groq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    async def capture(_system: str, user: str, **_kwargs) -> str:
        prompts.append(user)
        return "A compact factual description."

    monkeypatch.setattr(summarizer, "generate_text", capture)

    result = await summarizer.shorten_summary("Long Game", "x" * 10_000)

    assert result == "A compact factual description."
    assert len(prompts[0]) <= 4_100
