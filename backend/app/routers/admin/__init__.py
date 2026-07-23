"""Admin / internal debug endpoints.

Developer/ops use only — NOT part of the public product API. Every endpoint
requires an admin JWT (router-level `require_admin_user`); production should
additionally restrict /admin/* at the network/proxy layer.

Concerns are split one module per surface:
  health       — provider health + per-source smoke tests
  dashboard    — traffic dashboard + audit trail
  jobs         — data fill, primary-score backfill, consolidation
  diagnostics  — read-only per-game inspection
  matching     — external-id matching
  prices       — single-game price imports
"""

from fastapi import APIRouter, Depends

from ...security import require_admin_user
from . import dashboard, diagnostics, health, jobs, matching, prices

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_user)],
)

for _sub_router in (
    health.router,
    dashboard.router,
    jobs.router,
    diagnostics.router,
    matching.router,
    prices.router,
):
    router.include_router(_sub_router)

__all__ = ["router"]
