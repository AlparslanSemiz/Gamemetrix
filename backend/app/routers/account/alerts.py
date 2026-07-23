"""Per-alert read/dismissed state."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session

from ...account_security import AccountPrincipal, require_csrf
from ...database import get_db
from ...services.account_state import AccountStateLimitError, AlertState, set_alert_states
from .schemas import MAX_ALERT_KEY_LENGTH, AlertStateBulkPayload, AlertStatePayload

router = APIRouter(prefix="/alert-state")


def _store(db: Session, user_id: str, keys: list[str], state: AlertState) -> Response:
    try:
        set_alert_states(db, user_id, keys, state)
    except AccountStateLimitError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("", status_code=status.HTTP_204_NO_CONTENT)
def update_alert_states(
    payload: AlertStateBulkPayload,
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    return _store(db, principal.user.id, payload.keys, payload.state)


@router.put("/{alert_key}", status_code=status.HTTP_204_NO_CONTENT)
def update_alert_state(
    payload: AlertStatePayload,
    alert_key: str = Path(..., min_length=1, max_length=MAX_ALERT_KEY_LENGTH),
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    return _store(db, principal.user.id, [alert_key], payload.state)
