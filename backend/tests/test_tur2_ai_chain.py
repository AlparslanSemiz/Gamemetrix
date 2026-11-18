"""AI chain behaviour added in the 2026-11 audit: pacing, settlement, credential block."""

import asyncio
import logging
from collections import deque
from types import SimpleNamespace

import httpx
import pytest

from app.integrations import ai, groq, openrouter
from app.integrations.ai_types import (
    ErrorCategory,
    GenerationRequest,
    GenerationResult,
    ProviderFailure,
    mark_request_dispatched,
)
from tests.test_ai_fallback import _Limiter, _request, _result, _settings


class _Scripted:
    """Provider whose generate() runs a caller-supplied coroutine function."""

    def __init__(self, name, behaviour, *, slot=None):
        self._name = name
        self._behaviour = behaviour
        self.calls = 0
        if slot is not None:
            self.wait_for_slot = slot

    name = property(lambda self: self._name)
    model = property(lambda self: f"{self._name}/model")

    def is_configured(self):
        return True

    async def generate(self, request, timeout_seconds):
        self.calls += 1
        return await self._behaviour(request, timeout_seconds)


@pytest.fixture(autouse=True)
def _clean_inflight(monkeypatch):
    limiter = _Limiter()
    ai._inflight.clear()
    monkeypatch.setattr(ai, "get_rate_limiter", lambda: limiter)
    return limiter


@pytest.fixture(autouse=True)
def _settings_and_state(monkeypatch, _clean_inflight):
    monkeypatch.setattr(ai, "get_settings", _settings)
    ai._last_outcome.clear()
    yield
    ai._last_outcome.clear()


@pytest.mark.asyncio
async def test_rejected_credentials_block_the_provider_for_six_hours_with_one_error(
    monkeypatch, caplog, _clean_inflight
) -> None:
    async def reject(_request, _timeout):
        raise ProviderFailure(ErrorCategory.AUTHENTICATION, status_code=401)

    async def fine(_request, _timeout):
        return _result("gemini")

    groq_provider = _Scripted("groq", reject)
    gemini_provider = _Scripted("gemini", fine)
    monkeypatch.setattr(ai, "_ordered_providers", lambda: [groq_provider, gemini_provider])

    with caplog.at_level(logging.WARNING):
        assert await ai._run_chain(_request(), 60) == "ok"

    assert _clean_inflight.blocked == [("Groq", 6 * 3600)]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "credentials_rejected" in errors[0].getMessage()
    assert ai.provider_health("groq", True) == "degraded"
    assert ai.provider_health("gemini", True) == "ready"
    assert ai.provider_health("groq", False) == "unconfigured"


@pytest.mark.asyncio
async def test_timeout_before_any_request_leaves_returns_the_reservation(
    monkeypatch, _clean_inflight
) -> None:
    async def never_sends(_request, _timeout):
        await asyncio.sleep(5)  # stuck before the network call: nothing was dispatched

    provider = _Scripted("groq", never_sends)
    monkeypatch.setattr(ai, "_ordered_providers", lambda: [provider])
    monkeypatch.setattr(ai, "get_settings", lambda: _with_timeout(0.05))
    monkeypatch.setattr(ai, "_MAX_ATTEMPTS", 1)

    assert await ai._run_chain(_request(), 60) is None
    (source, reserved, actual) = _clean_inflight.settled[0]
    assert (source, actual) == ("Groq", 0) and reserved > 0


@pytest.mark.asyncio
async def test_timeout_after_dispatch_keeps_the_reservation(monkeypatch, _clean_inflight) -> None:
    async def sends_then_hangs(_request, _timeout):
        mark_request_dispatched()
        await asyncio.sleep(5)

    provider = _Scripted("groq", sends_then_hangs)
    monkeypatch.setattr(ai, "_ordered_providers", lambda: [provider])
    monkeypatch.setattr(ai, "get_settings", lambda: _with_timeout(0.05))
    monkeypatch.setattr(ai, "_MAX_ATTEMPTS", 1)

    assert await ai._run_chain(_request(), 60) is None
    assert _clean_inflight.settled == []


@pytest.mark.asyncio
async def test_provider_spacing_wait_does_not_eat_the_call_timeout(monkeypatch, _clean_inflight) -> None:
    order: list[str] = []

    async def slot():
        order.append("slot")
        await asyncio.sleep(0.3)  # longer than the 0.1 s per-call timeout below

    async def fast(_request, _timeout):
        order.append("generate")
        return _result("groq")

    provider = _Scripted("groq", fast, slot=slot)
    monkeypatch.setattr(ai, "_ordered_providers", lambda: [provider])
    monkeypatch.setattr(ai, "get_settings", lambda: _with_timeout(0.1))

    assert await ai._run_chain(_request(), 60) == "ok"
    assert order == ["slot", "generate"]
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_json_mode_rejection_falls_back_instead_of_stopping(monkeypatch) -> None:
    async def json_400(request, _timeout):
        raise groq.json_mode_rejection(
            request,
            ProviderFailure(ErrorCategory.INVALID_REQUEST, status_code=400, fallback_allowed=False),
        )

    async def fine(_request, _timeout):
        return GenerationResult(text='{"a":1}', provider="gemini", model="m")

    monkeypatch.setattr(
        ai, "_ordered_providers", lambda: [_Scripted("groq", json_400), _Scripted("gemini", fine)]
    )
    request = GenerationRequest("s", "u", 100, 0.2, json_object=True)

    assert await ai._run_chain(request, 60) == '{"a":1}'


def test_json_mode_rejection_only_rewrites_json_requests() -> None:
    plain = GenerationRequest("s", "u", 100, 0.2)
    failure = ProviderFailure(ErrorCategory.INVALID_REQUEST, status_code=400, fallback_allowed=False)
    assert groq.json_mode_rejection(plain, failure) is failure


class _Client:
    def __init__(self, calls, response):
        self.calls, self.response = calls, response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return None

    async def post(self, url, **kwargs):
        self.calls.append(kwargs)
        return self.response


@pytest.mark.asyncio
async def test_groq_requests_low_reasoning_and_a_token_floor(monkeypatch) -> None:
    calls: list[dict] = []
    settings = SimpleNamespace(
        GROQ_API_KEY="k",
        GROQ_MODEL="openai/gpt-oss-20b",
        GROQ_MIN_REQUEST_INTERVAL_SECONDS=0.0,
        groq_configured=lambda: True,
    )
    response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "x"}}]},
        request=httpx.Request("POST", "https://example.test"),
    )
    monkeypatch.setattr(groq, "get_settings", lambda: settings)
    monkeypatch.setattr(groq.httpx, "AsyncClient", lambda **_k: _Client(calls, response))

    await groq.GroqProvider().generate(GenerationRequest("s", "u", 8, 0.2), 5)

    body = calls[0]["json"]
    assert body["reasoning_effort"] == "low"
    assert body["max_tokens"] == 256


@pytest.mark.asyncio
async def test_groq_json_400_becomes_invalid_response(monkeypatch) -> None:
    settings = SimpleNamespace(
        GROQ_API_KEY="k",
        GROQ_MODEL="m",
        GROQ_MIN_REQUEST_INTERVAL_SECONDS=0.0,
        groq_configured=lambda: True,
    )
    response = httpx.Response(
        400, json={"error": {"message": "json mode unsupported"}},
        request=httpx.Request("POST", "https://example.test"),
    )
    monkeypatch.setattr(groq, "get_settings", lambda: settings)
    monkeypatch.setattr(groq.httpx, "AsyncClient", lambda **_k: _Client([], response))

    with pytest.raises(ProviderFailure) as raised:
        await groq.GroqProvider().generate(GenerationRequest("s", "u", 100, 0.2, json_object=True), 5)

    assert raised.value.category is ErrorCategory.INVALID_RESPONSE
    assert raised.value.fallback_allowed is True


@pytest.mark.asyncio
async def test_openrouter_applies_the_token_floor(monkeypatch) -> None:
    calls: list[dict] = []
    settings = SimpleNamespace(
        OPENROUTER_API_KEY="k", OPENROUTER_MODEL="m", openrouter_configured=lambda: True
    )
    response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "x"}}]},
        request=httpx.Request("POST", "https://example.test"),
    )
    monkeypatch.setattr(openrouter, "get_settings", lambda: settings)
    monkeypatch.setattr(openrouter.httpx, "AsyncClient", lambda **_k: _Client(calls, response))

    await openrouter.OpenRouterProvider().generate(GenerationRequest("s", "u", 96, 0.2), 5)

    assert calls[0]["json"]["max_tokens"] == 256


def test_groq_dead_helpers_are_gone() -> None:
    assert not hasattr(groq, "_used_tokens")
    assert not hasattr(groq, "_extract_text")


def _with_timeout(seconds: float) -> SimpleNamespace:
    cfg = _settings()
    cfg.AI_PROVIDER_TIMEOUT_SECONDS = seconds
    return cfg
