from types import SimpleNamespace

import httpx
import pytest

from app.integrations import groq
from app.services.summarizer import ai as summarizer_ai


class _Limiter:
    def __init__(self, allowed: bool = True):
        self.allowed = allowed
        self.sources: list[str] = []
        self.reserved: list[int] = []
        self.settled: list[tuple[int, int]] = []

    async def acquire(self, source: str, estimated_tokens: int = 0) -> bool:
        self.sources.append(source)
        self.reserved.append(estimated_tokens)
        return self.allowed

    def settle_tokens(self, _source: str, reserved: int, actual: int) -> None:
        self.settled.append((reserved, actual))


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
            json={
                "choices": [{"message": {"content": '{"verdict":"OK"}'}}],
                "usage": {"total_tokens": 137},
            },
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
    # A worst-case reservation up front, settled against the reported usage.
    assert limiter.reserved[0] > 400
    assert limiter.settled == [(limiter.reserved[0], 137)]


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
    # Nothing was spent, so nothing is settled.
    assert limiter.settled == []


@pytest.mark.asyncio
async def test_a_failed_groq_call_returns_its_whole_token_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = _Limiter()
    settings = SimpleNamespace(
        GROQ_API_KEY="test-key",
        GROQ_MODEL="openai/gpt-oss-20b",
        GROQ_MIN_REQUEST_INTERVAL_SECONDS=0.0,
        groq_configured=lambda: True,
    )

    class _FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url: str, **_kwargs) -> httpx.Response:
            return httpx.Response(500, request=httpx.Request("POST", url))

    monkeypatch.setattr(groq, "get_settings", lambda: settings)
    monkeypatch.setattr(groq, "get_rate_limiter", lambda: limiter)
    monkeypatch.setattr(groq.httpx, "AsyncClient", lambda **_kwargs: _FailingClient())
    monkeypatch.setattr(groq, "_last_request_started", 0.0)

    assert await groq.generate_text("system", "user") is None
    reserved = limiter.reserved[0]
    assert limiter.settled == [(reserved, 0)]


def test_token_estimate_covers_prompt_and_worst_case_output() -> None:
    estimate = groq.estimate_tokens("s" * 400, "u" * 800, 300)

    # 1,200 prompt chars ≈ 300 tokens, + overhead, + the full output allowance.
    assert 600 <= estimate <= 700


@pytest.mark.asyncio
async def test_summary_generation_bounds_provider_text_before_groq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    async def capture(_system: str, user: str, **_kwargs) -> str:
        prompts.append(user)
        return "A compact factual description."

    monkeypatch.setattr(summarizer_ai, "generate_text", capture)

    result = await summarizer_ai.shorten_summary("Long Game", "x" * 10_000)

    assert result == "A compact factual description."
    assert len(prompts[0]) <= 2_100
