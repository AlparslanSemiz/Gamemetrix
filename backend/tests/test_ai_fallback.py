import asyncio
import logging
from collections import deque
from types import SimpleNamespace

import pytest

from app.integrations import ai
from app.integrations.ai_types import (
    ErrorCategory,
    GenerationRequest,
    GenerationResult,
    ProviderFailure,
)


class _Provider:
    def __init__(
        self,
        name: str,
        outcomes: list[GenerationResult | ProviderFailure],
        *,
        configured: bool = True,
    ) -> None:
        self._name = name
        self._outcomes = deque(outcomes)
        self._configured = configured
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return f"{self._name}/model"

    def is_configured(self) -> bool:
        return self._configured

    async def generate(
        self,
        _request: GenerationRequest,
        _timeout_seconds: float,
    ) -> GenerationResult:
        self.calls += 1
        outcome = self._outcomes.popleft()
        if isinstance(outcome, ProviderFailure):
            raise outcome
        return outcome

    def classify_error(self, *_args):
        raise AssertionError("not used by orchestrator tests")


def _result(provider: str, text: str = "ok") -> GenerationResult:
    return GenerationResult(text=text, provider=provider, model=f"{provider}/model")


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        AI_PROVIDER_TIMEOUT_SECONDS=10.0,
        AI_BACKGROUND_DEADLINE_SECONDS=60.0,
        AI_INTERACTIVE_DEADLINE_SECONDS=15.0,
        AI_PROVIDER_ORDER=["groq", "gemini", "cloudflare", "openrouter"],
        GROQ_MODEL="groq/model",
        GEMINI_MODEL="gemini/model",
        CLOUDFLARE_MODEL="cloudflare/model",
        OPENROUTER_MODEL="openrouter/model",
    )


@pytest.fixture(autouse=True)
def _clean_inflight() -> None:
    ai._inflight.clear()


@pytest.mark.asyncio
async def test_groq_success_stops_the_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    groq = _Provider("groq", [_result("groq")])
    gemini = _Provider("gemini", [_result("gemini")])
    monkeypatch.setattr(ai, "_ordered_providers", lambda: [groq, gemini])

    result = await ai._run_chain(_request(), 60)

    assert result == "ok"
    assert groq.calls == 1
    assert gemini.calls == 0


@pytest.mark.asyncio
async def test_transient_failures_retry_then_follow_provider_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transient = ProviderFailure(ErrorCategory.RATE_LIMITED, retryable=True)
    groq = _Provider("groq", [transient, transient])
    gemini = _Provider("gemini", [transient, transient])
    cloudflare = _Provider(
        "cloudflare",
        [
            ProviderFailure(ErrorCategory.SERVER, status_code=503, retryable=True),
            ProviderFailure(ErrorCategory.SERVER, status_code=503, retryable=True),
        ],
    )
    openrouter = _Provider("openrouter", [_result("openrouter", "last fallback")])
    monkeypatch.setattr(
        ai,
        "_ordered_providers",
        lambda: [groq, gemini, cloudflare, openrouter],
    )

    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setattr(ai.asyncio, "sleep", no_wait)
    monkeypatch.setattr(ai.random, "uniform", lambda _low, _high: 0.0)

    result = await ai._run_chain(_request(), 60)

    assert result == "last fallback"
    assert [groq.calls, gemini.calls, cloudflare.calls, openrouter.calls] == [2, 2, 2, 1]


@pytest.mark.asyncio
async def test_permanent_auth_failure_falls_back_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groq = _Provider(
        "groq",
        [ProviderFailure(ErrorCategory.AUTHENTICATION, status_code=401)],
    )
    gemini = _Provider("gemini", [_result("gemini")])
    monkeypatch.setattr(ai, "_ordered_providers", lambda: [groq, gemini])

    assert await ai._run_chain(_request(), 60) == "ok"
    assert groq.calls == 1
    assert gemini.calls == 1


@pytest.mark.asyncio
async def test_shared_invalid_request_stops_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groq = _Provider(
        "groq",
        [
            ProviderFailure(
                ErrorCategory.INVALID_REQUEST,
                status_code=400,
                fallback_allowed=False,
            )
        ],
    )
    gemini = _Provider("gemini", [_result("gemini")])
    monkeypatch.setattr(ai, "_ordered_providers", lambda: [groq, gemini])

    assert await ai._run_chain(_request(), 60) is None
    assert groq.calls == 1
    assert gemini.calls == 0


@pytest.mark.asyncio
async def test_malformed_json_and_missing_fields_fall_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groq = _Provider("groq", [_result("groq", "```json\n{\"verdict\":\"OK\"}\n```")])
    gemini = _Provider("gemini", [_result("gemini", "{\"wrong\":true}")])
    cloudflare = _Provider(
        "cloudflare",
        [_result("cloudflare", "{\"verdict\":\"OK\"}")],
    )
    monkeypatch.setattr(
        ai,
        "_ordered_providers",
        lambda: [groq, gemini, cloudflare],
    )
    request = _request(
        json_object=True,
        validator=lambda value: '"verdict"' in value,
    )

    result = await ai._run_chain(request, 60)

    # A single fenced object is accepted and normalized, so later providers stay idle.
    assert result == '{"verdict":"OK"}'
    assert [groq.calls, gemini.calls, cloudflare.calls] == [1, 0, 0]

    groq = _Provider("groq", [_result("groq", "explanation {\"verdict\":\"OK\"}")])
    gemini = _Provider("gemini", [_result("gemini", "{\"wrong\":true}")])
    cloudflare = _Provider(
        "cloudflare",
        [_result("cloudflare", "{\"verdict\":\"OK\"}")],
    )
    monkeypatch.setattr(
        ai,
        "_ordered_providers",
        lambda: [groq, gemini, cloudflare],
    )

    assert await ai._run_chain(request, 60) == '{"verdict":"OK"}'
    assert [groq.calls, gemini.calls, cloudflare.calls] == [1, 1, 1]


@pytest.mark.asyncio
async def test_missing_provider_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    groq = _Provider("groq", [], configured=False)
    gemini = _Provider("gemini", [_result("gemini")])
    monkeypatch.setattr(ai, "_ordered_providers", lambda: [groq, gemini])

    assert await ai._run_chain(_request(), 60) == "ok"
    assert groq.calls == 0
    assert gemini.calls == 1


@pytest.mark.asyncio
async def test_identical_concurrent_requests_share_one_inflight_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = asyncio.Event()

    class _SlowProvider(_Provider):
        async def generate(self, request, timeout_seconds):
            self.calls += 1
            await gate.wait()
            return _result("groq", "shared")

    provider = _SlowProvider("groq", [])
    monkeypatch.setattr(ai, "get_settings", _settings)
    monkeypatch.setattr(ai, "_ordered_providers", lambda: [provider])

    first = asyncio.create_task(ai.generate_text("system", "same prompt"))
    second = asyncio.create_task(ai.generate_text("system", "same prompt"))
    await asyncio.sleep(0)
    gate.set()

    assert await asyncio.gather(first, second) == ["shared", "shared"]
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_logs_never_include_secrets_prompts_or_raw_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "sk-sensitive-api-key"
    prompt = "private user prompt"
    provider_error = "provider echoed sensitive body"
    provider = _Provider(
        "groq",
        [
            ProviderFailure(ErrorCategory.AUTHENTICATION, status_code=401),
        ],
    )
    monkeypatch.setattr(ai, "_ordered_providers", lambda: [provider])
    caplog.set_level(logging.INFO, logger="app.integrations.ai")

    assert await ai._run_chain(_request(user_prompt=prompt), 60) is None

    output = caplog.text
    assert "authentication" in output
    assert secret not in output
    assert prompt not in output
    assert provider_error not in output


@pytest.mark.asyncio
async def test_retry_after_is_honored_once(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _Provider(
        "gemini",
        [
            ProviderFailure(
                ErrorCategory.RATE_LIMITED,
                status_code=429,
                retryable=True,
                retry_after=2.5,
            ),
            _result("gemini"),
        ],
    )
    monkeypatch.setattr(ai, "_ordered_providers", lambda: [provider])
    delays: list[float] = []

    async def record_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(ai.asyncio, "sleep", record_sleep)

    assert await ai._run_chain(_request(), 60) == "ok"
    assert delays == [2.5]
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_retry_after_beyond_deadline_skips_retry_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groq = _Provider(
        "groq",
        [
            ProviderFailure(
                ErrorCategory.RATE_LIMITED,
                status_code=429,
                retryable=True,
                retry_after=120.0,
            )
        ],
    )
    gemini = _Provider("gemini", [_result("gemini")])
    monkeypatch.setattr(ai, "_ordered_providers", lambda: [groq, gemini])

    assert await ai._run_chain(_request(), 1) == "ok"
    assert groq.calls == 1
    assert gemini.calls == 1


@pytest.mark.asyncio
async def test_all_provider_failures_return_safe_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = [
        _Provider(
            name,
            [ProviderFailure(ErrorCategory.AUTHENTICATION, status_code=401)],
        )
        for name in ("groq", "gemini", "cloudflare", "openrouter")
    ]
    monkeypatch.setattr(ai, "_ordered_providers", lambda: providers)

    assert await ai._run_chain(_request(), 60) is None
    assert [provider.calls for provider in providers] == [1, 1, 1, 1]


def _request(
    *,
    json_object: bool = False,
    validator=None,
    user_prompt: str = "user",
) -> GenerationRequest:
    return GenerationRequest(
        system_prompt="system",
        user_prompt=user_prompt,
        max_output_tokens=100,
        temperature=0.2,
        json_object=json_object,
        response_validator=validator,
    )
