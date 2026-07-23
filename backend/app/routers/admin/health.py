"""Provider health probing and per-source live smoke tests."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import UTC, datetime, timedelta
from enum import Enum

from fastapi import APIRouter, HTTPException, Query

from ...integrations.cheapshark_service import cheapshark_service
from ...integrations.igdb_service import igdb_service
from ...integrations.itad_service import itad_service
from ...integrations.opencritic_service import opencritic_service
from ...integrations.rawg_service import rawg_service
from ...integrations.steam_service import steam_service
from ...integrations.types import SourceHealth

router = APIRouter()

_HEALTH_CHECK_TIMEOUT = 15
_SOURCE_TEST_TIMEOUT = 20

# Health probes make live calls to metered providers (OpenCritic bills for
# overage), and the dashboard requests them on every mount. A short TTL turned
# "leaving the admin tab open" into steady quota burn, so the cached result is
# held far longer; ?force=true still forces a live probe on demand.
_API_HEALTH_CACHE_TTL = timedelta(minutes=30)
_api_health_cache: tuple[datetime, dict[str, dict[str, object]]] | None = None

_HEALTH_CHECKS = {
    "igdb": igdb_service,
    "rawg": rawg_service,
    "opencritic": opencritic_service,
    "steam": steam_service,
    "itad": itad_service,
    "cheapshark": cheapshark_service,
}


class SourceTest(str, Enum):
    igdb = "igdb"
    rawg = "rawg"
    opencritic = "opencritic"
    steam = "steam"
    itad = "itad"
    cheapshark = "cheapshark"


@router.get("/api-health")
async def api_health(force: bool = Query(default=False)) -> dict:
    """Masked health status for every configured API source; secrets never included."""
    global _api_health_cache
    now = datetime.now(UTC)
    if not force and _api_health_cache is not None and now - _api_health_cache[0] < _API_HEALTH_CACHE_TTL:
        return _api_health_cache[1]

    results = await asyncio.gather(
        *(_safe_health_check(label, service) for label, service in _HEALTH_CHECKS.items())
    )
    payload = {health.source: _health_payload(health) for health in results}
    _api_health_cache = (now, payload)
    return payload


async def _safe_health_check(label: str, service) -> SourceHealth:
    try:
        return await asyncio.wait_for(service.health_check(), timeout=_HEALTH_CHECK_TIMEOUT)
    except asyncio.TimeoutError:
        return SourceHealth(
            source=label,
            configured=True,
            working=False,
            status="timeout",
            message=f"Health check timed out after {_HEALTH_CHECK_TIMEOUT}s",
        )
    except Exception as exc:
        return SourceHealth(
            source=label,
            configured=True,
            working=False,
            status="failing",
            message=f"Unexpected error: {type(exc).__name__}",
        )


def _health_payload(health: SourceHealth) -> dict[str, object]:
    return {
        "configured": health.configured,
        "working": health.working,
        "status": health.status,
        **({"message": health.message} if health.message else {}),
        **({"latency_ms": health.latency_ms} if health.latency_ms is not None else {}),
    }


@router.get("/source-test/{source}")
async def source_test(
    source: SourceTest,
    q: str = Query(default="Portal 2", min_length=2, max_length=120, description="Title to search for"),
) -> dict:
    """Run a live search against one source and return the normalized result."""
    try:
        result = await asyncio.wait_for(_run_source_test(source, q), timeout=_SOURCE_TEST_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Source test for '{source.value}' timed out")

    if result is None:
        return {"source": source.value, "query": q, "found": False, "result": None}
    return {"source": source.value, "query": q, "found": True, "result": _serialize(result)}


async def _run_source_test(source: SourceTest, q: str):
    match source:
        case SourceTest.igdb:
            return await igdb_service.search_game(q)
        case SourceTest.rawg:
            return await rawg_service.search_game(q)
        case SourceTest.opencritic:
            return await opencritic_service.search_game(q)
        case SourceTest.steam:
            app_id = await steam_service.lookup_app_id("", q)
            return await steam_service.get_app_details(app_id) if app_id else None
        case SourceTest.itad:
            itad_id = await itad_service.lookup_id(q)
            return itad_service.normalize_for_external_id(itad_id, q) if itad_id else None
        case SourceTest.cheapshark:
            deals = await cheapshark_service.search_deals(q, limit=3)
            return [cheapshark_service.normalize_deal(deal) for deal in deals] if deals else None


def _serialize(result: object) -> object:
    if hasattr(result, "__dataclass_fields__"):
        return dataclasses.asdict(result)
    if isinstance(result, list):
        return [dataclasses.asdict(item) if hasattr(item, "__dataclass_fields__") else item for item in result]
    return result
