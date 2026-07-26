"""OpenRouter free-model fallback adapter."""

from __future__ import annotations

import httpx

from ..config import get_settings
from .ai_types import (
    ErrorCategory,
    GenerationRequest,
    GenerationResult,
    ProviderFailure,
    classify_http_error,
    extract_openai_text,
    openai_total_tokens,
    transport_failure,
)
from .http_retry import DEFAULT_HEADERS

_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider:
    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def model(self) -> str:
        return get_settings().OPENROUTER_MODEL

    def is_configured(self) -> bool:
        return get_settings().openrouter_configured()

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
        headers = {
            **DEFAULT_HEADERS,
            "Authorization": f"Bearer {cfg.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload: dict[str, object] = {
            "model": cfg.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.json_object:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    _CHAT_COMPLETIONS_URL,
                    headers=headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise transport_failure(exc) from None
        try:
            data = response.json()
        except ValueError:
            data = None
        if not response.is_success:
            raise self.classify_error(response.status_code, data, response.headers)
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            error = data["error"]
            code = error.get("code")
            if isinstance(code, int):
                raise self.classify_error(code, data, response.headers)
            raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
        return GenerationResult(
            text=extract_openai_text(data),
            provider=self.name,
            model=cfg.OPENROUTER_MODEL,
            total_tokens=openai_total_tokens(data),
        )
