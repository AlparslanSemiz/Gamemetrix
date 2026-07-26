"""Gemini GenerateContent adapter using the existing async HTTP stack."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import quote

import httpx

from ..config import get_settings
from .ai_types import (
    ErrorCategory,
    GenerationRequest,
    GenerationResult,
    ProviderFailure,
    classify_http_error,
    transport_failure,
)
from .http_retry import DEFAULT_HEADERS

_API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
_NO_THINKING_MODELS = frozenset(
    {
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    }
)
_request_lock = asyncio.Lock()
_last_request_started = 0.0


class GeminiProvider:
    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return get_settings().GEMINI_MODEL

    def is_configured(self) -> bool:
        return get_settings().gemini_configured()

    def classify_error(
        self,
        status_code: int,
        payload: object | None,
        headers: httpx.Headers,
    ) -> ProviderFailure:
        return classify_http_error(status_code, payload, headers)

    async def generate(
        self,
        request: GenerationRequest,
        timeout_seconds: float,
    ) -> GenerationResult:
        if not self.is_configured():
            raise ProviderFailure(ErrorCategory.NOT_CONFIGURED)

        cfg = get_settings()
        url = f"{_API_ROOT}/{quote(cfg.GEMINI_MODEL, safe='')}:generateContent"
        generation_config: dict[str, object] = {
            "maxOutputTokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.json_object:
            generation_config["responseMimeType"] = "application/json"
        if cfg.GEMINI_MODEL in _NO_THINKING_MODELS:
            generation_config["thinkingConfig"] = {"thinkingBudget": 0}

        payload = {
            "systemInstruction": {
                "parts": [{"text": request.system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": request.user_prompt}],
                }
            ],
            "generationConfig": generation_config,
        }
        headers = {
            **DEFAULT_HEADERS,
            "Content-Type": "application/json",
            "x-goog-api-key": cfg.GEMINI_API_KEY,
        }

        async with _request_lock:
            await _wait_for_request_slot(cfg.GEMINI_MIN_REQUEST_INTERVAL_SECONDS)
            try:
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                raise transport_failure(exc) from None

        try:
            data = response.json()
        except ValueError:
            data = None
        if not response.is_success:
            raise self.classify_error(response.status_code, data, response.headers)
        return GenerationResult(
            text=_extract_text(data),
            provider=self.name,
            model=cfg.GEMINI_MODEL,
            total_tokens=_total_tokens(data),
        )


async def _wait_for_request_slot(interval_seconds: float) -> None:
    global _last_request_started
    wait_seconds = interval_seconds - (time.monotonic() - _last_request_started)
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)
    _last_request_started = time.monotonic()


def _extract_text(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    first = candidates[0]
    if not isinstance(first, dict):
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    content = first.get("content")
    if not isinstance(content, dict):
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    texts = [
        part["text"]
        for part in parts
        if isinstance(part, dict)
        and isinstance(part.get("text"), str)
        and part["text"].strip()
    ]
    text = "".join(texts).strip()
    if not text:
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    return text


def _total_tokens(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    usage = payload.get("usageMetadata")
    if not isinstance(usage, dict):
        return 0
    total = usage.get("totalTokenCount")
    return total if isinstance(total, int) and total >= 0 else 0
