"""
Groq text-generation integration.

Thin async HTTP client over Groq's OpenAI-compatible chat-completions endpoint.
Used to rewrite long game descriptions into a short summary (see
services/summarizer.py). Requires GROQ_API_KEY in .env (free key at
https://console.groq.com/keys); the model is selected via GROQ_MODEL. No
third-party SDK — plain httpx, matching the other integration clients.
"""

import logging

import httpx

from ..config import get_settings
from .http_retry import DEFAULT_HEADERS

log = logging.getLogger(__name__)

_GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_HTTP_TIMEOUT = 20
_MAX_OUTPUT_TOKENS = 400
_TEMPERATURE = 0.7


async def generate_text(system_prompt: str, user_prompt: str) -> str | None:
    """Return Groq's response text for the prompt, or None when unavailable."""
    cfg = get_settings()
    if not cfg.groq_configured():
        return None

    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {cfg.GROQ_API_KEY}"}
    payload = {
        "model": cfg.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": _MAX_OUTPUT_TOKENS,
        "temperature": _TEMPERATURE,
    }

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(_GROQ_API_URL, headers=headers, json=payload)
        if not resp.is_success:
            log.debug("Groq request failed: %s", resp.status_code)
            return None
        data = resp.json()
    except Exception:
        log.debug("Groq request errored", exc_info=True)
        return None

    if not isinstance(data, dict):
        return None
    return _extract_text(data)


def _extract_text(data: dict[str, object]) -> str | None:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    return content.strip()
