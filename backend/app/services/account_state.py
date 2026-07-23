from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..account_security import utcnow
from ..models import Game, User, UserAlertState, UserCollection, UserPreference

AlertState = Literal["read", "dismissed"]
CollectionType = Literal[
    "watchlist",
    "playing",
    "seen",
    "completed",
    "liked",
    "favorites",
]
COLLECTION_TYPES: tuple[CollectionType, ...] = (
    "watchlist",
    "playing",
    "seen",
    "completed",
    "liked",
    "favorites",
)

_RESERVED_SETTING_KEYS = frozenset({"guest_state_merged", "gm_guest_state_merged"})
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_SLUG_LENGTH = 180
_MAX_ALERT_KEY_LENGTH = 240
_MAX_ACCOUNT_STATE_ROWS = 10_000
_MAX_SETTINGS_JSON_LENGTH = 10_000


class AccountStateLimitError(ValueError):
    pass


@dataclass(frozen=True)
class GuestPreferences:
    min_discount: int
    min_score: int
    upcoming_days: int
    email_digest_enabled: bool
    marketing_enabled: bool
    settings: dict[str, object]


@dataclass(frozen=True)
class GuestState:
    collections: dict[CollectionType, list[str]]
    preferences: GuestPreferences
    read_alerts: list[str]
    dismissed_alerts: list[str]


def account_payload(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "email_verified": user.email_verified_at is not None,
        "created_at": user.created_at.isoformat(),
    }


def get_or_create_preference(db: Session, user_id: str) -> UserPreference:
    preference = db.get(UserPreference, user_id)
    if preference is not None:
        return preference
    preference = UserPreference(
        user_id=user_id,
        alert_min_discount=20,
        alert_min_score=80,
        alert_upcoming_days=45,
        email_digest_enabled=False,
        marketing_enabled=False,
        settings={},
        updated_at=utcnow(),
    )
    db.add(preference)
    db.flush()
    return preference


def account_state_payload(db: Session, user: User) -> dict[str, object]:
    collections: dict[str, list[str]] = {
        collection_type: [] for collection_type in COLLECTION_TYPES
    }
    rows = db.execute(
        select(UserCollection.collection_type, Game.slug)
        .join(Game, Game.id == UserCollection.game_id)
        .where(UserCollection.user_id == user.id)
        .order_by(UserCollection.created_at)
    ).all()
    for collection_type, slug in rows:
        if collection_type in collections:
            collections[collection_type].append(slug)

    preference = get_or_create_preference(db, user.id)
    alert_rows = db.scalars(
        select(UserAlertState).where(UserAlertState.user_id == user.id)
    ).all()
    db.commit()
    return {
        "account": account_payload(user),
        "collections": collections,
        "preferences": _preference_payload(preference),
        "read_alerts": [
            row.alert_key for row in alert_rows if row.state == "read"
        ],
        "dismissed_alerts": [
            row.alert_key for row in alert_rows if row.state == "dismissed"
        ],
    }


def merge_guest_state(
    db: Session,
    user: User,
    state: GuestState,
) -> dict[str, object]:
    now = utcnow()
    _merge_collections(db, user.id, state.collections, now)
    _merge_preferences(db, user.id, state.preferences, now)
    _merge_alerts(
        db,
        user.id,
        read_alerts=state.read_alerts,
        dismissed_alerts=state.dismissed_alerts,
        now=now,
    )
    db.commit()
    return account_state_payload(db, user)


def add_to_collection(
    db: Session,
    user_id: str,
    collection_type: CollectionType,
    slug: str,
) -> bool:
    """Returns False when no game owns that slug."""
    game = db.scalar(select(Game).where(Game.slug == slug))
    if game is None:
        return False
    already_present = db.scalar(
        select(UserCollection).where(
            UserCollection.user_id == user_id,
            UserCollection.game_id == game.id,
            UserCollection.collection_type == collection_type,
        )
    )
    if already_present is None:
        db.add(
            UserCollection(
                user_id=user_id,
                game_id=game.id,
                collection_type=collection_type,
                created_at=utcnow(),
            )
        )
        db.commit()
    return True


def remove_from_collection(
    db: Session,
    user_id: str,
    collection_type: CollectionType,
    slug: str,
) -> None:
    db.execute(
        delete(UserCollection).where(
            UserCollection.user_id == user_id,
            UserCollection.collection_type == collection_type,
            UserCollection.game_id == select(Game.id).where(Game.slug == slug).scalar_subquery(),
        )
    )
    db.commit()


def set_alert_states(
    db: Session,
    user_id: str,
    keys: list[str],
    state: AlertState,
) -> None:
    rows = {
        row.alert_key: row
        for row in db.scalars(
            select(UserAlertState).where(
                UserAlertState.user_id == user_id,
                UserAlertState.alert_key.in_(keys),
            )
        ).all()
    }
    existing_count = db.scalar(
        select(func.count(UserAlertState.id)).where(UserAlertState.user_id == user_id)
    ) or 0
    if existing_count + len(set(keys) - set(rows)) > _MAX_ACCOUNT_STATE_ROWS:
        raise AccountStateLimitError("Account alert history limit reached.")

    now = utcnow()
    for key in keys:
        row = rows.get(key)
        if row is None:
            db.add(
                UserAlertState(
                    user_id=user_id,
                    alert_key=key,
                    state=state,
                    updated_at=now,
                )
            )
        else:
            row.state = state
            row.updated_at = now
    db.commit()


def sanitized_settings(
    current: dict[str, object],
    incoming: dict[str, object],
) -> dict[str, object]:
    if len(json.dumps(incoming)) > _MAX_SETTINGS_JSON_LENGTH:
        raise AccountStateLimitError("Settings payload is too large.")
    merged = dict(current)
    merged.update(
        {
            key: value
            for key, value in incoming.items()
            if key not in _RESERVED_SETTING_KEYS
        }
    )
    return merged


def _preference_payload(preference: UserPreference) -> dict[str, object]:
    return {
        "min_discount": preference.alert_min_discount,
        "min_score": preference.alert_min_score,
        "upcoming_days": preference.alert_upcoming_days,
        "email_digest_enabled": preference.email_digest_enabled,
        "marketing_enabled": preference.marketing_enabled,
        "settings": {
            key: value
            for key, value in (preference.settings or {}).items()
            if key not in _RESERVED_SETTING_KEYS
        },
    }


def _valid_slugs(values: list[str]) -> set[str]:
    return {
        value
        for value in values
        if len(value) <= _MAX_SLUG_LENGTH and _SLUG_PATTERN.fullmatch(value)
    }


def _merge_collections(
    db: Session,
    user_id: str,
    collections: dict[CollectionType, list[str]],
    now: datetime,
) -> None:
    valid_by_type = {
        collection_type: _valid_slugs(collections[collection_type])
        for collection_type in COLLECTION_TYPES
    }
    all_slugs = set().union(*valid_by_type.values())
    games = (
        {
            game.slug: game
            for game in db.scalars(
                select(Game).where(Game.slug.in_(all_slugs))
            ).all()
        }
        if all_slugs
        else {}
    )
    existing = {
        (row.game_id, row.collection_type)
        for row in db.scalars(
            select(UserCollection).where(UserCollection.user_id == user_id)
        ).all()
    }
    for collection_type, slugs in valid_by_type.items():
        for slug in slugs:
            game = games.get(slug)
            key = (game.id, collection_type) if game else None
            if game is None or key in existing:
                continue
            db.add(
                UserCollection(
                    user_id=user_id,
                    game_id=game.id,
                    collection_type=collection_type,
                    created_at=now,
                )
            )
            existing.add((game.id, collection_type))


def _merge_preferences(
    db: Session,
    user_id: str,
    incoming: GuestPreferences,
    now: datetime,
) -> None:
    preference = get_or_create_preference(db, user_id)
    settings = dict(preference.settings or {})
    if settings.get("gm_guest_state_merged") or settings.get("guest_state_merged"):
        return

    preference.alert_min_discount = incoming.min_discount
    preference.alert_min_score = incoming.min_score
    preference.alert_upcoming_days = incoming.upcoming_days
    preference.email_digest_enabled = incoming.email_digest_enabled
    preference.marketing_enabled = incoming.marketing_enabled
    if len(json.dumps(incoming.settings)) <= _MAX_SETTINGS_JSON_LENGTH:
        settings.update(
            {
                key: value
                for key, value in incoming.settings.items()
                if key not in _RESERVED_SETTING_KEYS
            }
        )
    settings.pop("guest_state_merged", None)
    settings["gm_guest_state_merged"] = True
    preference.settings = settings
    preference.updated_at = now


def _merge_alerts(
    db: Session,
    user_id: str,
    *,
    read_alerts: list[str],
    dismissed_alerts: list[str],
    now: datetime,
) -> None:
    current = {
        row.alert_key: row
        for row in db.scalars(
            select(UserAlertState).where(UserAlertState.user_id == user_id)
        ).all()
    }
    incoming_keys = {
        key
        for keys in (read_alerts, dismissed_alerts)
        for key in keys
        if key and len(key) <= _MAX_ALERT_KEY_LENGTH
    }
    if len(current) + len(incoming_keys - set(current)) > _MAX_ACCOUNT_STATE_ROWS:
        raise AccountStateLimitError("Account alert history limit reached.")

    for state_name, keys in (
        ("read", read_alerts),
        ("dismissed", dismissed_alerts),
    ):
        for key in set(keys):
            if not key or len(key) > _MAX_ALERT_KEY_LENGTH:
                continue
            row = current.get(key)
            if row is None:
                row = UserAlertState(
                    user_id=user_id,
                    alert_key=key,
                    state=state_name,
                    updated_at=now,
                )
                db.add(row)
                current[key] = row
            elif state_name == "dismissed" or row.state != "dismissed":
                row.state = state_name
                row.updated_at = now
