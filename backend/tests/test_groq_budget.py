from types import SimpleNamespace

import httpx
import pytest

from app.integrations import groq
from app.integrations.ai_types import GenerationRequest
from app.services.summarizer import ai as summarizer_ai


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
async def test_groq_adapter_builds_json_request_and_reports_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    settings = SimpleNamespace(
        GROQ_API_KEY="test-key",
        GROQ_MODEL="openai/gpt-oss-20b",
        GROQ_MIN_REQUEST_INTERVAL_SECONDS=0.0,
        groq_configured=lambda: True,
    )
    monkeypatch.setattr(groq, "get_settings", lambda: settings)
    monkeypatch.setattr(groq.httpx, "AsyncClient", lambda **_kwargs: _Client(calls))
    monkeypatch.setattr(groq, "_last_request_started", 0.0)
    request = GenerationRequest(
        system_prompt="Return JSON.",
        user_prompt="Review this row.",
        max_output_tokens=400,
        temperature=0.2,
        json_object=True,
    )

    result = await groq.GroqProvider().generate(request, 10)

    assert result.text == '{"verdict":"OK"}'
    assert result.total_tokens == 137
    assert calls[0]["json"]["model"] == "openai/gpt-oss-20b"
    assert calls[0]["json"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_summary_generation_bounds_provider_text_before_ai_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    async def capture(_system: str, user: str, **_kwargs) -> str:
        prompts.append(user)
        return "A compact factual description."

    monkeypatch.setattr(summarizer_ai, "generate_text", capture)

    result = await summarizer_ai.shorten_summary("Long Game", "x" * 10_000)

    # The ungrounded, too-short model answer is rejected in favor of a bounded
    # extract from the supplied source.
    assert result != "A compact factual description."
    assert result.endswith(".")
    assert len(prompts[0]) <= 2_100
