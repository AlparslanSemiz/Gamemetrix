"""/api/account — user accounts, sessions, saved state and preferences."""

from fastapi import APIRouter, Depends

from ...account_security import require_account_enabled
from . import alerts, auth, oauth, preferences, state

router = APIRouter(
    prefix="/api/account",
    tags=["account"],
    dependencies=[Depends(require_account_enabled)],
)

for _sub_router in (auth.router, oauth.router, state.router, preferences.router, alerts.router):
    router.include_router(_sub_router)

router.add_api_route("", auth.delete_account, methods=["DELETE"])

__all__ = ["router"]
