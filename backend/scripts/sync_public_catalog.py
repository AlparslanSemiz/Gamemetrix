"""Synchronize local game rows from the public production catalog.

Production remains the source of truth. This intentionally copies only fields
returned by ``GET /api/games``. The default mode never deletes local rows or
touches accounts, analytics, provider budgets, or job state. Exact-mirror mode
can explicitly remove local-only games and their cascading related catalog rows.

Preview:
    python scripts/sync_public_catalog.py

Apply after taking a local PostgreSQL backup:
    python scripts/sync_public_catalog.py --apply

Make the local game set exactly match production:
    python scripts/sync_public_catalog.py --apply --prune-local-only
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from dotenv import load_dotenv
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from app.database import SessionLocal
from app.models import Game


_PAGE_SIZE = 500
_UPSERT_BATCH_SIZE = 250
_MAX_ATTEMPTS = 4
_MIN_REQUEST_INTERVAL_SECONDS = 0.22

_PUBLIC_GAME_FIELDS = frozenset(
    {
        "title",
        "slug",
        "summary",
        "summary_short",
        "cover_url",
        "release_date",
        "release_year",
        "early_access_date",
        "official_release_date",
        "metacritic_score",
        "image_url",
        "website_url",
        "ratings_refreshed_at",
        "metadata_refreshed_at",
        "prices_refreshed_at",
        "content_type",
        "metrix_score",
        "rank_score",
        "is_rankable",
        "seo_indexable",
        "seo_exclusion_reason",
        "seo_updated_at",
        "critic_score",
        "user_score",
        "genres",
        "platforms",
        "source_scores",
        "developer",
        "publisher",
        "steam_app_id",
        "game_modes",
        "playtime_minutes",
        "hltb_id",
        "hltb_url",
        "hltb_main_story_minutes",
        "hltb_main_extra_minutes",
        "hltb_completionist_minutes",
        "hltb_all_styles_minutes",
        "hltb_refreshed_at",
        "is_endless",
        "proton_tier",
        "proton_score",
        "award_count",
        "award_nominations",
        "goty_year",
        "awards",
        "screenshots",
        "system_requirements",
        "dlcs",
        "similar_games",
        "franchise",
    }
)

_DATE_FIELDS = frozenset(
    {"release_date", "early_access_date", "official_release_date"}
)
_DATETIME_FIELDS = frozenset(
    {
        "ratings_refreshed_at",
        "metadata_refreshed_at",
        "prices_refreshed_at",
        "seo_updated_at",
        "hltb_refreshed_at",
    }
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="https://gamemetrix.me",
        help="Production public origin (default: https://gamemetrix.me).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Upsert fetched rows. Without this flag the command only previews.",
    )
    parser.add_argument(
        "--prune-local-only",
        action="store_true",
        help="Delete local games absent from production (requires --apply and a backup).",
    )
    return parser.parse_args()


def _request_page(
    client: httpx.Client,
    endpoint: str,
    *,
    offset: int,
) -> dict[str, Any]:
    params = {
        "content_type": "all",
        "sort": "title",
        "direction": "asc",
        "limit": _PAGE_SIZE,
        "offset": offset,
    }
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = client.get(endpoint, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Catalog response was not an object.")
            return payload
        except (httpx.HTTPError, ValueError, RuntimeError):
            if attempt == _MAX_ATTEMPTS:
                raise
            time.sleep(2 ** (attempt - 1))
    raise AssertionError("unreachable")


def _fetch_catalog(base_url: str) -> tuple[list[dict[str, Any]], int]:
    endpoint = urljoin(base_url.rstrip("/") + "/", "api/games")
    games: list[dict[str, Any]] = []
    expected_total: int | None = None
    offset = 0
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        while expected_total is None or offset < expected_total:
            started = time.monotonic()
            payload = _request_page(client, endpoint, offset=offset)
            page = payload.get("games")
            total = payload.get("total")
            if not isinstance(page, list) or not isinstance(total, int):
                raise RuntimeError("Catalog response is missing games or total.")
            if expected_total is None:
                expected_total = total
                print(f"production_total={expected_total}", flush=True)
            elif total != expected_total:
                raise RuntimeError(
                    f"Production total changed during export ({expected_total} -> {total}); retry."
                )
            if not page and offset < expected_total:
                raise RuntimeError(f"Catalog page at offset {offset} was unexpectedly empty.")
            games.extend(page)
            offset += len(page)
            if offset % 5_000 == 0 or offset >= expected_total:
                print(f"fetched={offset}", flush=True)
            elapsed = time.monotonic() - started
            if elapsed < _MIN_REQUEST_INTERVAL_SECONDS:
                time.sleep(_MIN_REQUEST_INTERVAL_SECONDS - elapsed)

    assert expected_total is not None
    slugs = [row.get("slug") for row in games]
    if len(games) != expected_total:
        raise RuntimeError(f"Fetched {len(games)} rows, expected {expected_total}.")
    if any(not isinstance(slug, str) or not slug for slug in slugs):
        raise RuntimeError("Production catalog contains an invalid slug.")
    if len(set(slugs)) != expected_total:
        raise RuntimeError("Production catalog contains duplicate slugs.")
    return games, expected_total


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"Expected an ISO date, got {type(value).__name__}.")
    return date.fromisoformat(value)


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"Expected an ISO datetime, got {type(value).__name__}.")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _game_values(payload: dict[str, Any]) -> dict[str, Any]:
    values = {
        key: value
        for key, value in payload.items()
        if key in _PUBLIC_GAME_FIELDS
    }
    missing = {"title", "slug", "summary", "cover_url", "release_date"} - values.keys()
    if missing:
        raise RuntimeError(f"Production game is missing required fields: {sorted(missing)}")
    for field in _DATE_FIELDS:
        if field in values:
            values[field] = _parse_date(values[field])
    for field in _DATETIME_FIELDS:
        if field in values:
            values[field] = _parse_datetime(values[field])
    return values


def _local_diff(
    production_slugs: set[str],
) -> tuple[int, list[str], list[str]]:
    with SessionLocal() as db:
        local_slugs = set(db.scalars(select(Game.slug)).all())
    missing = sorted(production_slugs - local_slugs)
    local_only = sorted(local_slugs - production_slugs)
    return len(local_slugs), missing, local_only


def _upsert_games(games: list[dict[str, Any]]) -> int:
    values = [_game_values(game) for game in games]
    update_fields = sorted(_PUBLIC_GAME_FIELDS - {"slug"})
    with SessionLocal() as db:
        for start in range(0, len(values), _UPSERT_BATCH_SIZE):
            batch = values[start : start + _UPSERT_BATCH_SIZE]
            statement = insert(Game).values(batch)
            statement = statement.on_conflict_do_update(
                index_elements=[Game.slug],
                set_={
                    field: getattr(statement.excluded, field)
                    for field in update_fields
                },
            )
            db.execute(statement)
            db.commit()
            completed = min(start + len(batch), len(values))
            if completed % 5_000 == 0 or completed == len(values):
                print(f"upserted={completed}", flush=True)
        return int(db.scalar(select(func.count(Game.id))) or 0)


def _prune_local_only(production_slugs: set[str]) -> int:
    with SessionLocal() as db:
        local_only_ids = [
            int(game_id)
            for game_id, slug in db.execute(select(Game.id, Game.slug))
            if slug not in production_slugs
        ]
        for start in range(0, len(local_only_ids), _UPSERT_BATCH_SIZE):
            batch = local_only_ids[start : start + _UPSERT_BATCH_SIZE]
            db.execute(delete(Game).where(Game.id.in_(batch)))
            db.commit()
        return len(local_only_ids)


def main() -> None:
    args = _arguments()
    if args.prune_local_only and not args.apply:
        raise SystemExit("--prune-local-only requires --apply.")
    games, production_total = _fetch_catalog(args.base_url)
    production_slugs = {str(game["slug"]) for game in games}
    local_total, missing, local_only = _local_diff(production_slugs)
    print(f"local_before={local_total}")
    print(f"missing_local={len(missing)}")
    print(f"local_only={len(local_only)}")
    if missing:
        print(f"missing_sample={','.join(missing[:10])}")
    if local_only:
        print(f"local_only_sample={','.join(local_only[:10])}")

    if not args.apply:
        print("preview_only=true")
        return

    local_after = _upsert_games(games)
    _, remaining_missing, _ = _local_diff(production_slugs)
    if remaining_missing:
        raise RuntimeError(
            f"Synchronization left {len(remaining_missing)} production games missing."
        )
    pruned = (
        _prune_local_only(production_slugs)
        if args.prune_local_only
        else 0
    )
    final_total, final_missing, final_local_only = _local_diff(production_slugs)
    if final_missing:
        raise RuntimeError(
            f"Synchronization left {len(final_missing)} production games missing."
        )
    if args.prune_local_only and final_local_only:
        raise RuntimeError(
            f"Exact-mirror synchronization left {len(final_local_only)} local-only games."
        )
    print(f"production_total={production_total}")
    print(f"local_after_upsert={local_after}")
    print(f"pruned_local_only={pruned}")
    print(f"local_after={final_total}")
    print(f"local_only_after={len(final_local_only)}")
    print("synchronized=true")


if __name__ == "__main__":
    main()
