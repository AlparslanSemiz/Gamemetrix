"""Per-API source overview: role, config, weight, budget, and driving loop."""

from __future__ import annotations

from fastapi import APIRouter

from ...services.api_sources import api_sources_status

router = APIRouter()


@router.get("/api-sources")
def get_api_sources() -> dict[str, object]:
    return api_sources_status()
