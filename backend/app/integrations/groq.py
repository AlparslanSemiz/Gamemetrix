"""
Groq text-generation integration.

Thin async HTTP client over Groq's OpenAI-compatible chat-completions endpoint.
Used for bounded catalog text tasks such as description auditing and quality
classification. Requires GROQ_API_KEY in .env (free key at
https://console.groq.com/keys); the model is selected via GROQ_MODEL. No
third-party SDK — plain httpx, matching the other integration clients.

Persistent budgeting, concurrency and request bounds are enforced by the
central AI orchestrator rather than by this transport adapter.
"""

import asyncio
import logging
import time

import httpx

from ..config import get_settings
from .ai_types import (
    ErrorCategory,
    GenerationRequest,
    GenerationResult,
    ProviderFailure,
    classify_http_error,
    MIN_OPENAI_COMPAT_OUTPUT_TOKENS,
    extract_openai_text,
    json_mode_rejection,
    mark_request_dispatched,
    openai_total_tokens,
    transport_failure,
)
from .http_retry import DEFAULT_HEADERS

log = logging.getLogger(__name__)

_GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_HTTP_TIMEOUT = 20
_MAX_OUTPUT_TOKENS = 400
_TEMPERATURE = 0.7
_request_lock = asyncio.Lock()
_last_request_started = 0.0


async def generate_text(
    system_prompt: str,
    user_prompt: str,
    *,
    max_output_tokens: int = _MAX_OUTPUT_TOKENS,
    temperature: float = _TEMPERATURE,
    json_object: bool = False,
) -> str | None:
    """Compatibility wrapper routed through centralized controls and fallback."""
    from .ai import generate_text as generate_with_controls

    return await generate_with_controls(
        system_prompt,
        user_prompt,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        json_object=json_object,
    )


class GroqProvider:
    @property
    def name(self) -> str:
        return "groq"

    @property
    def model(self) -> str:
        return get_settings().GROQ_MODEL

    def is_configured(self) -> bool:
        return get_settings().groq_configured()

    def classify_error(
        self,
        status_code: int,
        payload: object | None,
        headers: httpx.Headers,
    ) -> ProviderFailure:
        return classify_http_error(status_code, payload, headers)

    async def wait_for_slot(self) -> None:
        """Space request starts by GROQ_MIN_REQUEST_INTERVAL_SECONDS (free-tier pacing)."""
        async with _request_lock:
            await _wait_for_request_slot(get_settings().GROQ_MIN_REQUEST_INTERVAL_SECONDS)

    async def generate(
        self,
        request: GenerationRequest,
        timeout_seconds: float,
    ) -> GenerationResult:
        if not self.is_configured():
            raise ProviderFailure(ErrorCategory.NOT_CONFIGURED)

        cfg = get_settings()
        # The minimum-interval wait happens in wait_for_slot(), before the orchestrator
        # reserves budget and starts its per-call timeout. Waiting here used to eat
        # that timeout, so queued calls timed out before any HTTP request left.
        async with _request_lock:
            try:
                headers = {
                    **DEFAULT_HEADERS,
                    "Authorization": f"Bearer {cfg.GROQ_API_KEY}",
                }
                payload: dict[str, object] = {
                    "model": cfg.GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": request.system_prompt},
                        {"role": "user", "content": request.user_prompt},
                    ],
                    "max_tokens": max(request.max_output_tokens, MIN_OPENAI_COMPAT_OUTPUT_TOKENS),
                    "temperature": request.temperature,
                }
                if "gpt-oss" in cfg.GROQ_MODEL:
                    payload["reasoning_effort"] = "low"
                if request.json_object:
                    payload["response_format"] = {"type": "json_object"}
                mark_request_dispatched()
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    response = await client.post(
                        _GROQ_API_URL,
                        headers=headers,
                        json=payload,
                    )
                try:
                    data = response.json()
                except ValueError:
                    data = None
                if not response.is_success:
                    raise json_mode_rejection(
                        request,
                        self.classify_error(response.status_code, data, response.headers),
                    )
                text = extract_openai_text(data)
                return GenerationResult(
                    text=text,
                    provider=self.name,
                    model=cfg.GROQ_MODEL,
                    total_tokens=openai_total_tokens(data),
                )
            except httpx.HTTPError as exc:
                raise transport_failure(exc) from None


async def _wait_for_request_slot(interval_seconds: float) -> None:
    global _last_request_started
    wait_seconds = interval_seconds - (time.monotonic() - _last_request_started)
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)
    _last_request_started = time.monotonic()
