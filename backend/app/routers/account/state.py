"""Account-wide state: read, guest merge, export, and collection membership."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session

from ...account_security import AccountPrincipal, require_account_principal, require_csrf, utcnow
from ...database import get_db
from ...services.account_state import (
    COLLECTION_TYPES,
    AccountStateLimitError,
    CollectionType,
    GuestPreferences,
    GuestState,
    account_state_payload,
    add_to_collection,
    merge_guest_state,
    remove_from_collection,
)
from .schemas import MergePayload

router = APIRouter()

_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_MAX_SLUG_LENGTH = 180


def _slug_path() -> Path:
    return Path(..., min_length=1, max_length=_MAX_SLUG_LENGTH, pattern=_SLUG_PATTERN)


@router.get("/state")
def account_state(
    principal: AccountPrincipal = Depends(require_account_principal),
    db: Session = Depends(get_db),
) -> dict:
    return account_state_payload(db, principal.user)


@router.post("/state/merge")
def merge_account_state(
    payload: MergePayload,
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return merge_guest_state(db, principal.user, _guest_state(payload))
    except AccountStateLimitError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _guest_state(payload: MergePayload) -> GuestState:
    return GuestState(
        collections={
            collection_type: getattr(payload.collections, collection_type)
            for collection_type in COLLECTION_TYPES
        },
        preferences=GuestPreferences(
            min_discount=payload.preferences.min_discount,
            min_score=payload.preferences.min_score,
            upcoming_days=payload.preferences.upcoming_days,
            email_digest_enabled=payload.preferences.email_digest_enabled,
            marketing_enabled=payload.preferences.marketing_enabled,
            settings=dict(payload.preferences.settings),
        ),
        read_alerts=payload.read_alerts,
        dismissed_alerts=payload.dismissed_alerts,
    )


@router.put("/collections/{collection_type}/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def add_collection_item(
    collection_type: CollectionType,
    slug: str = _slug_path(),
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    if not add_to_collection(db, principal.user.id, collection_type, slug):
        raise HTTPException(status_code=404, detail="Game not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/collections/{collection_type}/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def remove_collection_item(
    collection_type: CollectionType,
    slug: str = _slug_path(),
    principal: AccountPrincipal = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    remove_from_collection(db, principal.user.id, collection_type, slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/export")
def export_account(
    principal: AccountPrincipal = Depends(require_account_principal),
    db: Session = Depends(get_db),
) -> dict:
    return {
        "exported_at": utcnow().isoformat(),
        **account_state_payload(db, principal.user),
    }
