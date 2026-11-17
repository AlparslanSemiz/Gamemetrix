"""Central text-generation registry, retry policy, fallback, and deduplication."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import re
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from ..config import Settings, get_settings
from .ai_types import (
    AIProvider,
    ErrorCategory,
    GenerationRequest,
    ProviderFailure,
    ResponseValidator,
    begin_dispatch_tracking,
    end_dispatch_tracking,
)
from .cloudflare_ai import CloudflareAIProvider
from .gemini import GeminiProvider
from .groq import GroqProvider
from .openrouter import OpenRouterProvider
from .rate_limiter import get_rate_limiter

log = logging.getLogger(__name__)

_DEFAULT_MAX_OUTPUT_TOKENS = 800
_DEFAULT_TEMPERATURE = 0.7
_MAX_ATTEMPTS = 2
_BACKOFF_SECONDS = 1.0
_JITTER_SECONDS = 0.25
_JSON_FENCE = re.compile(r"\A```(?:json)?\s*(\{.*\})\s*```\Z", re.DOTALL | re.IGNORECASE)

_inflight: dict[str, asyncio.Task[str | None]] = {}
_inflight_lock = asyncio.Lock()
_chain_semaphore: asyncio.Semaphore | None = None
_chain_semaphore_loop: asyncio.AbstractEventLoop | None = None

_PROVIDER_BUDGET_SOURCES = {
    "groq": "Groq",
    "gemini": "Gemini",
    "cloudflare": "CloudflareAI",
    "openrouter": "OpenRouter",
}
_DEFINITE_NO_CHARGE_FAILURES = frozenset(
    {
        ErrorCategory.RATE_LIMITED,
        ErrorCategory.AUTHENTICATION,
        ErrorCategory.PERMISSION,
        ErrorCategory.INVALID_MODEL,
        ErrorCategory.INVALID_REQUEST,
        ErrorCategory.NOT_CONFIGURED,
    }
)
_CHARS_PER_TOKEN = 4
# A rejected key does not heal by itself; stop spending 12 s + a doomed request on it
# for every call and let the chain go straight to the next provider.
_CREDENTIAL_BLOCK_SECONDS = 6 * 3600
_CREDENTIAL_FAILURES = frozenset({ErrorCategory.AUTHENTICATION, ErrorCategory.PERMISSION})

# provider name -> (category value, unix time) of its most recent outcome.
_last_outcome: dict[str, tuple[str, float]] = {}
_PROMPT_OVERHEAD_TOKENS = 40


async def generate_text(
    system_prompt: str,
    user_prompt: str,
    *,
    max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS,
    temperature: float = _DEFAULT_TEMPERATURE,
    json_object: bool = False,
    response_validator: ResponseValidator | None = None,
    deadline_seconds: float | None = None,
) -> str | None:
    """Generate normalized text through the configured non-recursive fallback chain."""
    cfg = get_settings()
    bounded_system, bounded_user = _bounded_prompts(system_prompt, user_prompt, cfg)
    request = GenerationRequest(
        system_prompt=bounded_system,
        user_prompt=bounded_user,
        max_output_tokens=min(
            cfg.AI_MAX_OUTPUT_TOKENS,
            max(1, int(max_output_tokens)),
        ),
        temperature=float(temperature),
        json_object=json_object,
        response_validator=response_validator,
    )
    total_deadline = (
        cfg.AI_BACKGROUND_DEADLINE_SECONDS
        if deadline_seconds is None
        else max(0.1, float(deadline_seconds))
    )
    key = _request_key(request, total_deadline, cfg)

    async with _inflight_lock:
        task = _inflight.get(key)
        if task is None:
            task = asyncio.create_task(_run_chain_bounded(request, total_deadline))
            _inflight[key] = task
            task.add_done_callback(
                lambda completed, request_key=key: asyncio.create_task(
                    _remove_inflight(request_key, completed)
                )
            )

    try:
        return await asyncio.shield(task)
    finally:
        if task.done():
            async with _inflight_lock:
                if _inflight.get(key) is task:
                    _inflight.pop(key, None)


async def _remove_inflight(key: str, task: asyncio.Task[str | None]) -> None:
    async with _inflight_lock:
        if _inflight.get(key) is task:
            _inflight.pop(key, None)


async def _run_chain_bounded(
    request: GenerationRequest,
    deadline_seconds: float,
) -> str | None:
    try:
        async with asyncio.timeout(deadline_seconds):
            async with _ai_chain_semaphore():
                return await _run_chain(request, deadline_seconds)
    except TimeoutError:
        return None


def _ai_chain_semaphore() -> asyncio.Semaphore:
    global _chain_semaphore, _chain_semaphore_loop
    loop = asyncio.get_running_loop()
    if _chain_semaphore is None or _chain_semaphore_loop is not loop:
        _chain_semaphore = asyncio.Semaphore(get_settings().AI_MAX_CONCURRENCY)
        _chain_semaphore_loop = loop
    return _chain_semaphore


def last_provider_outcome(provider: str) -> tuple[str, float] | None:
    """(category, unix time) of the provider's most recent attempt, if any this process."""
    return _last_outcome.get(provider)


def _last_outcome_fields(provider: str) -> dict[str, object]:
    outcome = _last_outcome.get(provider)
    if outcome is None:
        return {"last_outcome": None, "last_outcome_at": None}
    category, at = outcome
    return {
        "last_outcome": category,
        "last_outcome_at": datetime.fromtimestamp(at, tz=UTC).isoformat(),
    }


def provider_health(provider: str, configured: bool) -> str:
    """'unconfigured', 'degraded' (last attempt failed) or 'ready'.

    A key being present says nothing about whether it works: a rejected key used to
    show as ready for as long as the process lived.
    """
    if not configured:
        return "unconfigured"
    outcome = _last_outcome.get(provider)
    if outcome is not None and outcome[0] != "ok":
        return "degraded"
    return "ready"


def provider_statuses(cfg: Settings | None = None) -> list[dict[str, object]]:
    settings = cfg or get_settings()
    configured = {
        "groq": settings.groq_configured(),
        "gemini": settings.gemini_configured(),
        "cloudflare": settings.cloudflare_ai_configured(),
        "openrouter": settings.openrouter_configured(),
    }
    models = {
        "groq": settings.GROQ_MODEL,
        "gemini": settings.GEMINI_MODEL,
        "cloudflare": settings.CLOUDFLARE_MODEL,
        "openrouter": settings.OPENROUTER_MODEL,
    }
    return [
        {
            "provider": name,
            "model": models[name],
            "configured": configured[name],
            "position": position,
            "health": provider_health(name, configured[name]),
            **_last_outcome_fields(name),
        }
        for position, name in enumerate(settings.AI_PROVIDER_ORDER, start=1)
    ]


async def _run_chain(request: GenerationRequest, deadline_seconds: float) -> str | None:
    request_id = uuid.uuid4().hex
    started = time.monotonic()
    deadline_at = started + deadline_seconds
    providers = _ordered_providers()
    configured = [provider for provider in providers if provider.is_configured()]
    if not configured:
        _log_failure(
            request_id=request_id,
            provider="none",
            model="none",
            attempt=0,
            duration_ms=0,
            category=ErrorCategory.NOT_CONFIGURED,
            status_code=None,
            fallback=False,
        )
        return None

    for provider_index, provider in enumerate(configured):
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            remaining = deadline_at - time.monotonic()
            if remaining <= 0:
                _log_failure(
                    request_id=request_id,
                    provider=provider.name,
                    model=provider.model,
                    attempt=attempt,
                    duration_ms=_elapsed_ms(started),
                    category=ErrorCategory.TIMEOUT,
                    status_code=None,
                    fallback=False,
                )
                return None

            source = _PROVIDER_BUDGET_SOURCES[provider.name]
            # Pace providers that need spacing between calls BEFORE reserving budget and
            # before the per-call timeout starts. The outer chain deadline still bounds it.
            await _await_provider_slot(provider, source)
            attempt_started = time.monotonic()
            remaining = deadline_at - attempt_started
            if remaining <= 0:
                return None
            reserved = estimate_tokens(request)
            try:
                acquired = await get_rate_limiter().acquire(
                    source,
                    estimated_tokens=reserved,
                )
            except Exception:
                log.exception(
                    "ai_request request_id=%s provider=%s model=%s "
                    "attempt=%d budget_acquire_failed=true",
                    request_id,
                    _log_value(provider.name),
                    _log_value(provider.model),
                    attempt,
                )
                return None
            if not acquired:
                failure = ProviderFailure(ErrorCategory.BUDGET_EXHAUSTED)
            else:
                dispatched, tracking_token = begin_dispatch_tracking()
                try:
                    timeout = min(get_settings().AI_PROVIDER_TIMEOUT_SECONDS, remaining)
                    result = await asyncio.wait_for(
                        provider.generate(request, timeout),
                        timeout=timeout,
                    )
                    if result.total_tokens > 0:
                        get_rate_limiter().settle_tokens(
                            source,
                            reserved,
                            result.total_tokens,
                        )
                    text = _validate_response(result.text, request)
                except TimeoutError:
                    failure = ProviderFailure(ErrorCategory.TIMEOUT, retryable=True)
                    if not dispatched[0]:
                        # Nothing left the process, so nothing can have been charged.
                        get_rate_limiter().settle_tokens(source, reserved, 0)
                except ProviderFailure as exc:
                    failure = exc
                    if exc.category in _DEFINITE_NO_CHARGE_FAILURES or exc.status_code == 400:
                        get_rate_limiter().settle_tokens(source, reserved, 0)
                    if exc.category in _CREDENTIAL_FAILURES:
                        _block_rejected_credentials(provider, source, exc)
                except Exception:
                    _log_failure(
                        request_id=request_id,
                        provider=provider.name,
                        model=provider.model,
                        attempt=attempt,
                        duration_ms=_elapsed_ms(attempt_started),
                        category=ErrorCategory.INTERNAL,
                        status_code=None,
                        fallback=False,
                    )
                    return None
                else:
                    _last_outcome[provider.name] = ("ok", time.time())
                    log.info(
                        "ai_request request_id=%s provider=%s model=%s attempt=%d "
                        "duration_ms=%d success=true status=200 category=ok fallback=%s",
                        request_id,
                        _log_value(result.provider),
                        _log_value(result.model),
                        attempt,
                        _elapsed_ms(attempt_started),
                        str(provider_index > 0).lower(),
                    )
                    return text
                finally:
                    end_dispatch_tracking(tracking_token)

            if acquired:
                _last_outcome[provider.name] = (failure.category.value, time.time())
            has_next = provider_index < len(configured) - 1
            will_retry = failure.retryable and attempt < _MAX_ATTEMPTS
            delay = 0.0
            if will_retry:
                delay = (
                    failure.retry_after
                    if failure.retry_after is not None
                    else _BACKOFF_SECONDS + random.uniform(0.0, _JITTER_SECONDS)
                )
                if delay >= deadline_at - time.monotonic():
                    will_retry = False
            will_fallback = failure.fallback_allowed and has_next and not will_retry
            _log_failure(
                request_id=request_id,
                provider=provider.name,
                model=provider.model,
                attempt=attempt,
                duration_ms=_elapsed_ms(attempt_started),
                category=failure.category,
                status_code=failure.status_code,
                fallback=will_fallback,
            )

            if not will_retry:
                if failure.fallback_allowed:
                    break
                return None

            await asyncio.sleep(delay)

    log.warning(
        "ai_request request_id=%s provider=none model=none attempt=0 "
        "duration_ms=%d success=false status=none category=all_failed fallback=false",
        request_id,
        _elapsed_ms(started),
    )
    return None


async def _await_provider_slot(provider: AIProvider, source: str) -> None:
    wait = getattr(provider, "wait_for_slot", None)
    if wait is None:
        return
    is_blocked = getattr(get_rate_limiter(), "is_blocked", None)
    if is_blocked is not None and is_blocked(source):
        return  # acquire() will refuse immediately; do not sleep for a provider we skip
    await wait()


def _block_rejected_credentials(
    provider: AIProvider,
    source: str,
    failure: ProviderFailure,
) -> None:
    """Stop calling a provider whose key was rejected (401/403) for six hours."""
    get_rate_limiter().block(source, _CREDENTIAL_BLOCK_SECONDS)
    log.error(
        "ai_provider_blocked provider=%s model=%s status=%s hours=%d "
        "reason=credentials_rejected; fix the key or drop it from AI_PROVIDER_ORDER",
        _log_value(provider.name),
        _log_value(provider.model),
        failure.status_code if failure.status_code is not None else "none",
        _CREDENTIAL_BLOCK_SECONDS // 3600,
    )


def estimate_tokens(request: GenerationRequest) -> int:
    """Reserve prompt estimate plus the full bounded output allowance."""
    prompt_chars = len(request.system_prompt) + len(request.user_prompt)
    return (
        prompt_chars // _CHARS_PER_TOKEN
        + _PROMPT_OVERHEAD_TOKENS
        + request.max_output_tokens
    )


def _bounded_prompts(
    system_prompt: str,
    user_prompt: str,
    cfg: Settings,
) -> tuple[str, str]:
    system = str(system_prompt)
    user = str(user_prompt)
    remaining = cfg.AI_MAX_PROMPT_CHARS - len(system)
    if remaining < 0:
        return system[: cfg.AI_MAX_PROMPT_CHARS], ""
    return system, user[:remaining]


def _ordered_providers() -> list[AIProvider]:
    registry: dict[str, Callable[[], AIProvider]] = {
        "groq": GroqProvider,
        "gemini": GeminiProvider,
        "cloudflare": CloudflareAIProvider,
        "openrouter": OpenRouterProvider,
    }
    return [registry[name]() for name in get_settings().AI_PROVIDER_ORDER]


def _validate_response(text: str, request: GenerationRequest) -> str:
    normalized = text.strip()
    if not normalized:
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    if request.json_object:
        normalized = _normalize_json_object(normalized)
    if request.response_validator is not None and not request.response_validator(normalized):
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    return normalized


def _normalize_json_object(text: str) -> str:
    fenced = _JSON_FENCE.fullmatch(text)
    candidate = fenced.group(1) if fenced else text
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE) from None
    if not isinstance(payload, dict):
        raise ProviderFailure(ErrorCategory.INVALID_RESPONSE)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _request_key(
    request: GenerationRequest,
    deadline_seconds: float,
    cfg: Settings,
) -> str:
    digest = hashlib.sha256()
    for value in (
        request.system_prompt,
        request.user_prompt,
        str(request.max_output_tokens),
        repr(request.temperature),
        str(request.json_object),
        repr(deadline_seconds),
        ",".join(cfg.AI_PROVIDER_ORDER),
        cfg.GROQ_MODEL,
        cfg.GEMINI_MODEL,
        cfg.CLOUDFLARE_MODEL,
        cfg.OPENROUTER_MODEL,
        _validator_identity(request.response_validator),
    ):
        digest.update(value.encode("utf-8", errors="replace"))
        digest.update(b"\0")
    return digest.hexdigest()


def _validator_identity(validator: ResponseValidator | None) -> str:
    if validator is None:
        return "none"
    return (
        f"{getattr(validator, '__module__', '')}:"
        f"{getattr(validator, '__qualname__', '')}:"
        f"{id(validator)}"
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _log_value(value: str) -> str:
    return "_".join(value.split())[:160] or "none"


def _log_failure(
    *,
    request_id: str,
    provider: str,
    model: str,
    attempt: int,
    duration_ms: int,
    category: ErrorCategory,
    status_code: int | None,
    fallback: bool,
) -> None:
    log.warning(
        "ai_request request_id=%s provider=%s model=%s attempt=%d duration_ms=%d "
        "success=false status=%s category=%s fallback=%s",
        request_id,
        _log_value(provider),
        _log_value(model),
        attempt,
        duration_ms,
        status_code if status_code is not None else "none",
        category.value,
        str(fallback).lower(),
    )
