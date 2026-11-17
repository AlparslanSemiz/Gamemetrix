"""Public-facing behaviour: provider status, error details, sitemap cache, rate-limit headers."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from app.integrations.google_oauth import GoogleOAuthError
from app.main import _rate_limited, app
from app.routers import seo
from app.routers.account import oauth
from app.services.game_query import json_array_values_statement
from app.models import Game


def test_integration_status_exposes_only_source_and_status() -> None:
    response = TestClient(app).get("/api/integrations/status")
    assert response.status_code == 200
    rows = response.json()
    assert rows
    for row in rows:
        assert set(row) == {"source", "status"}
    assert "_KEY" not in response.text and "_SECRET" not in response.text


def test_google_exchange_failure_does_not_leak_provider_detail(monkeypatch) -> None:
    async def failing(*_args, **_kwargs):
        raise GoogleOAuthError("token endpoint said client_secret=abc123")

    monkeypatch.setattr(oauth, "fetch_userinfo", failing)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(oauth._resolve_google_account(None, None, "code", "verifier"))
    assert caught.value.status_code == 502
    assert "abc123" not in str(caught.value.detail)


def test_sitemap_serves_last_good_copy_when_the_build_fails(monkeypatch) -> None:
    monkeypatch.setattr(seo, "_sitemap_memory", {})
    first = seo._sitemap_response("t", lambda: "<urlset>one</urlset>")
    assert first.headers["cache-control"] == "public, s-maxage=3600, stale-while-revalidate=86400"

    key = "t"
    stored_at, body = seo._sitemap_memory[key]
    seo._sitemap_memory[key] = (stored_at - timedelta(hours=1), body)  # expired

    def broken() -> str:
        raise RuntimeError("database is away")

    stale = seo._sitemap_response(key, broken)
    assert stale.body == b"<urlset>one</urlset>"
    with pytest.raises(RuntimeError):
        seo._sitemap_response("never-built", broken)


def test_sitemap_memory_hit_skips_the_build(monkeypatch) -> None:
    monkeypatch.setattr(seo, "_sitemap_memory", {"k": (datetime.now(UTC), "cached")})

    def must_not_run() -> str:
        raise AssertionError("fresh copy should be used")

    assert seo._sitemap_response("k", must_not_run).body == b"cached"


def test_rate_limit_response_is_429_with_retry_after() -> None:
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "app": app})
    request.state.view_rate_limit = None

    class _Limit:
        error_message = None
        limit = "1/minute"

    response = _rate_limited(request, RateLimitExceeded(_Limit()))
    assert response.status_code == 429
    assert response.headers["retry-after"]


def test_facet_arrays_tolerate_scalar_json_values() -> None:
    sql = str(json_array_values_statement(Game.genres))
    assert "jsonb_typeof" in sql
