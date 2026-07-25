from __future__ import annotations

import re
from datetime import UTC, datetime
from html import escape
from math import isfinite
from urllib.parse import quote
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from ..config import get_settings
from ..models import Game, PriceSnapshot


PRIMARY_SOURCES = frozenset({"Metacritic", "OpenCritic", "IGDB", "Steam"})
# Every Game column the catalog-wide pass below reads or writes, including the two
# feeding the applicable_primary_sources / live_primary_source_count properties.
# The heavy JSON blobs a game carries (screenshots, system_requirements, dlcs,
# similar_games, awards) are deliberately absent: nothing here looks at them and
# loading them for the whole catalog is what pushed the container past its limit.
_SEO_STATE_COLUMNS = (
    Game.content_type,
    Game.release_year,
    Game.cover_url,
    Game.image_url,
    Game.summary,
    Game.platforms,
    Game.source_scores,
    Game.proton_tier,
    Game.hltb_main_story_minutes,
    Game.hltb_all_styles_minutes,
    Game.award_count,
    Game.goty_year,
    Game.rank_score,
    Game.metrix_score,
    Game.seo_indexable,
    Game.seo_exclusion_reason,
    Game.seo_updated_at,
)
PLACEHOLDER_SUMMARY_MARKERS = (
    "cached from rawg search",
    "editorial metadata can be enriched",
    "summary is not available",
    "no description available",
)
CANONICAL_ORIGIN = "https://gamemetrix.me"


def _valid_https_url(value: str | None) -> bool:
    if not value or len(value) > 500 or any(char.isspace() or ord(char) < 32 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def _valid_live_primary_score(score: dict, applicable: frozenset[str]) -> bool:
    if score.get("status") != "live" or str(score.get("source")) not in applicable:
        return False
    try:
        value = float(score.get("score", 0) or 0)
    except (TypeError, ValueError):
        return False
    return isfinite(value) and 0 < value <= 100


def seo_exclusion_reason(game: Game, *, has_price_data: bool) -> str | None:
    if game.content_type != "game":
        return "not_a_game"
    if game.release_year <= 1970:
        return "unknown_release_date"
    if not any(_valid_https_url(value) for value in (game.cover_url, game.image_url)):
        return "missing_image"
    summary = " ".join((game.summary or "").split())
    if len(summary) < 160 or any(marker in summary.lower() for marker in PLACEHOLDER_SUMMARY_MARKERS):
        return "thin_summary"

    applicable = game.applicable_primary_sources
    live_primary = {
        str(score.get("source"))
        for score in (game.source_scores or [])
        if _valid_live_primary_score(score, applicable)
    }
    if len(live_primary) < 2:
        return "insufficient_primary_scores"

    has_context = bool(
        game.proton_tier
        or game.hltb_main_story_minutes
        or game.hltb_all_styles_minutes
        or game.award_count
        or game.goty_year
        or has_price_data
    )
    if not has_context:
        return "missing_decision_context"
    return None


def refresh_game_seo_state(
    game: Game,
    *,
    content_updated: bool = False,
    now: datetime | None = None,
) -> bool:
    quality_reason = seo_exclusion_reason(game, has_price_data=bool(game.price_snapshots))
    indexable = quality_reason is None and game.seo_indexable
    reason = quality_reason
    if quality_reason is None and not indexable:
        reason = "initial_index_limit"
    changed = game.seo_indexable != indexable or game.seo_exclusion_reason != reason
    game.seo_indexable = indexable
    game.seo_exclusion_reason = reason
    if changed or content_updated or game.seo_updated_at is None:
        game.seo_updated_at = now or datetime.now(UTC)
    return changed


def refresh_catalog_seo_states(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    timestamp = now or datetime.now(UTC)
    # seo_exclusion_reason only needs to know *whether* a game has priced data, so a
    # set of ids answers it in one cheap query. Eager-loading the snapshot collections
    # instead pulled every PriceSnapshot row for the whole catalog into memory and was
    # repeatedly OOM-killing the 400m backend container at startup.
    priced_game_ids = set(db.scalars(select(PriceSnapshot.game_id).distinct()))
    games = list(db.scalars(select(Game).options(load_only(*_SEO_STATE_COLUMNS))))
    quality_reasons = {
        game.id: seo_exclusion_reason(game, has_price_data=game.id in priced_game_ids)
        for game in games
    }
    eligible = [game for game in games if quality_reasons[game.id] is None]
    eligible.sort(
        key=lambda game: (game.rank_score, game.metrix_score, game.live_primary_source_count, game.release_year),
        reverse=True,
    )
    published_ids = {game.id for game in eligible[:get_settings().SEO_INDEX_LIMIT]}
    changed = 0
    for game in games:
        reason = quality_reasons[game.id]
        indexable = game.id in published_ids
        if reason is None and not indexable:
            reason = "initial_index_limit"
        if game.seo_indexable != indexable or game.seo_exclusion_reason != reason:
            game.seo_indexable = indexable
            game.seo_exclusion_reason = reason
            game.seo_updated_at = timestamp
            changed += 1
        elif game.seo_updated_at is None:
            game.seo_updated_at = timestamp
    return {"eligible": len(eligible), "indexable": len(published_ids), "changed": changed}


def game_canonical_url(game: Game) -> str:
    return f"{CANONICAL_ORIGIN}/game/{quote(game.slug)}"


def genre_slug(name: str) -> str:
    """"Massively Multiplayer" -> "massively-multiplayer" (the /best/<slug>-games segment)."""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def indexable_genre_facets(db: Session, minimum_games: int) -> list[tuple[str, str, int]]:
    """
    Genres worth a landing page, as (slug, display name, indexable game count).

    Derived from live catalogue data rather than a hand-written list, so the set
    grows with the catalogue and never advertises a page with nothing on it.
    """
    counts: dict[str, tuple[str, int]] = {}
    rows = db.scalars(
        select(Game.genres).where(Game.seo_indexable.is_(True), Game.content_type == "game")
    ).all()
    for genres in rows:
        for raw in genres or []:
            if not isinstance(raw, str):
                continue
            name = raw.strip()
            slug = genre_slug(name)
            if not slug:
                continue
            display, count = counts.get(slug, (name, 0))
            counts[slug] = (display, count + 1)
    return sorted(
        ((slug, display, count) for slug, (display, count) in counts.items() if count >= minimum_games),
        key=lambda row: (-row[2], row[0]),
    )


def sitemap_document(
    games: list[Game],
    years: list[int] | None = None,
    curated_paths: list[str] | None = None,
) -> str:
    rows = []
    for game in games:
        lastmod = ""
        if game.seo_updated_at:
            value = game.seo_updated_at
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            lastmod = f"<lastmod>{escape(value.date().isoformat())}</lastmod>"
        rows.append(
            "<url>"
            f"<loc>{escape(game_canonical_url(game))}</loc>"
            f"{lastmod}"
            "</url>"
        )
    static_urls = (
        f"{CANONICAL_ORIGIN}/",
        f"{CANONICAL_ORIGIN}/about",
        *(f"{CANONICAL_ORIGIN}{path}" for path in (curated_paths or [])),
        *(f"{CANONICAL_ORIGIN}/best/games/{year}" for year in (years or [])),
    )
    static_rows = "".join(
        f"<url><loc>{escape(url)}</loc></url>" for url in static_urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{static_rows}{''.join(rows)}"
        "</urlset>"
    )
