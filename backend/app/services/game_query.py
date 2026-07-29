"""
Catalog SQL query construction.

Builds the SELECT/COUNT statements behind GET /api/games and GET /api/facets so
route handlers stay pure orchestration. Every filter is expressed in SQL — no
result set is ever materialised for filtering.

Public API:
  CatalogFilters                          -> dataclass of advanced filter inputs
  build_catalog_query(...)                -> Select[tuple[Game]]
  build_catalog_count_query(...)          -> Select[tuple[int]]
  apply_advanced_filters(query, filters)  -> Select
  apply_sort(query, sort, direction)      -> Select[tuple[Game]]
  json_array_values_statement(column)     -> Select[tuple[str]]
  build_platform_filters(platforms)       -> set[str]
"""

import datetime
from dataclasses import dataclass

from sqlalchemy import (
    BigInteger,
    ColumnElement,
    Float,
    Select,
    and_,
    asc,
    case,
    cast,
    desc,
    exists,
    func,
    or_,
    select,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.expression import TableValuedAlias

from ..integrations.source_registry import CRITIC_SOURCES, PC_PLATFORM_KEYS, PRIMARY_SOURCES
from ..models import Game, PriceSnapshot
from .game_filter import LIKE_ESCAPE_CHAR, escape_like

_DEAL_FRESHNESS_HOURS = 24
_BEST_DEAL_MIN_DISCOUNT_PERCENT = 50
_MAX_REVIEW_COUNT = 2_000_000_000
_MAX_VALID_SCORE = 100
_MINUTES_PER_HOUR = 60

# Catalogs that predate the game_modes column still carry the signal in their
# genre tags, so a mode filter also accepts these equivalents.
_PLAYER_MODE_GENRE_ALIASES: dict[str, frozenset[str]] = {
    "multiplayer": frozenset({"massively multiplayer", "mmo", "mmorpg", "mmoarpg", "multiplayer", "pvp", "online co-op"}),
    "coop": frozenset({"co-op", "coop", "online co-op", "local co-op"}),
    "singleplayer": frozenset({"single player", "singleplayer"}),
}

_SOURCE_SORT_COLUMNS: dict[str, str] = {
    "metacritic_score": "Metacritic",
    "opencritic_score": "OpenCritic",
    "steam_score": "Steam",
}


@dataclass(frozen=True)
class CatalogFilters:
    """Advanced catalog filters that apply identically to the page and count queries."""

    genre: str | None = None
    developer: str | None = None
    publisher: str | None = None
    platform: str | None = None
    min_ratings: int | None = None
    max_ratings: int | None = None
    has_award: bool = False
    min_live_sources: int | None = None
    require_critic: bool = False
    player_mode: str | None = None
    playtime_min_hours: float | None = None
    playtime_max_hours: float | None = None


def build_catalog_query(
    content_type: str,
    q: str | None,
    year_min: int | None,
    year_max: int | None,
    min_score: float | None,
    max_score: float | None,
    deal: str,
    sort: str,
    direction: str,
) -> Select[tuple[Game]]:
    query = _apply_base_filters(
        select(Game), content_type, q, year_min, year_max, min_score, max_score, deal
    )
    return apply_sort(query, sort, direction)


def build_catalog_count_query(
    content_type: str,
    q: str | None,
    year_min: int | None,
    year_max: int | None,
    min_score: float | None,
    max_score: float | None,
    deal: str,
) -> Select[tuple[int]]:
    """Direct COUNT(*) so PostgreSQL can use an index-only scan."""
    return _apply_base_filters(
        select(func.count()).select_from(Game),
        content_type,
        q,
        year_min,
        year_max,
        min_score,
        max_score,
        deal,
    )


def _apply_base_filters(
    query: Select,
    content_type: str,
    q: str | None,
    year_min: int | None,
    year_max: int | None,
    min_score: float | None,
    max_score: float | None,
    deal: str,
) -> Select:
    if content_type != "all":
        query = query.where(Game.content_type == content_type)
    if q:
        query = query.where(Game.title.ilike(f"%{escape_like(q)}%", escape=LIKE_ESCAPE_CHAR))
    if year_min is not None:
        query = query.where(Game.release_year >= year_min)
    if year_max is not None:
        query = query.where(Game.release_year <= year_max)
    if min_score is not None:
        query = query.where(Game.metrix_score >= min_score)
    if max_score is not None:
        query = query.where(Game.metrix_score <= max_score)
    return _apply_deal_filter(query, deal)


def _apply_deal_filter(query: Select, deal: str) -> Select:
    fresh_before = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=_DEAL_FRESHNESS_HOURS)
    if deal == "free":
        free_price = exists(
            select(PriceSnapshot.id).where(
                PriceSnapshot.game_id == Game.id,
                PriceSnapshot.is_free.is_(True),
                PriceSnapshot.fetched_at >= fresh_before,
            )
        )
        return query.where(free_price)
    if deal == "best":
        discounted_price = exists(
            select(PriceSnapshot.id).where(
                PriceSnapshot.game_id == Game.id,
                PriceSnapshot.fetched_at >= fresh_before,
                or_(
                    PriceSnapshot.is_free.is_(True),
                    PriceSnapshot.discount_percent >= _BEST_DEAL_MIN_DISCOUNT_PERCENT,
                    (
                        PriceSnapshot.sale_price.is_not(None)
                        & PriceSnapshot.list_price.is_not(None)
                        & (PriceSnapshot.sale_price < PriceSnapshot.list_price)
                    ),
                ),
            )
        )
        return query.where(discounted_price)
    return query


def apply_sort(query: Select[tuple[Game]], sort: str, direction: str) -> Select[tuple[Game]]:
    score_tiebreakers = (desc(Game.rank_score), desc(Game.metrix_score), desc(Game.is_rankable), asc(Game.title), asc(Game.id))
    if sort == "title":
        col = desc(Game.title) if direction == "desc" else asc(Game.title)
        return query.order_by(col, desc(Game.rank_score), desc(Game.metrix_score), asc(Game.id))
    if sort == "release_year":
        col = desc(Game.release_year) if direction == "desc" else asc(Game.release_year)
        return query.order_by(col, desc(Game.rank_score), desc(Game.metrix_score), asc(Game.title), asc(Game.id))
    if sort == "critic_score":
        col = desc(Game.critic_score) if direction == "desc" else asc(Game.critic_score)
        return query.order_by(col, *score_tiebreakers)
    if sort == "user_score":
        col = desc(Game.user_score) if direction == "desc" else asc(Game.user_score)
        return query.order_by(col, *score_tiebreakers)
    if sort == "metrix_score":
        col = desc(Game.metrix_score) if direction == "desc" else asc(Game.metrix_score)
        return query.order_by(col, desc(Game.rank_score), desc(Game.is_rankable), asc(Game.title), asc(Game.id))
    if sort in _SOURCE_SORT_COLUMNS:
        source_score = _source_score_expression(_SOURCE_SORT_COLUMNS[sort])
        col = desc(source_score) if direction == "desc" else asc(source_score)
        return query.order_by(col, desc(Game.rank_score), desc(Game.metrix_score), asc(Game.title), asc(Game.id))
    if sort == "review_count":
        reviews = _review_count_expression(require_live_score=False)
        col = desc(reviews) if direction == "desc" else asc(reviews)
        return query.order_by(col, desc(Game.rank_score), desc(Game.metrix_score), asc(Game.title), asc(Game.id))
    # Default (rank_score) — reliability-weighted ranking
    col = desc(Game.rank_score) if direction == "desc" else asc(Game.rank_score)
    return query.order_by(col, desc(Game.metrix_score), desc(Game.is_rankable), asc(Game.title), asc(Game.id))


def apply_advanced_filters(query: Select, filters: CatalogFilters) -> Select:
    if filters.genre:
        query = query.where(_json_array_match(Game.genres, {filters.genre.strip().lower()}))
    if filters.developer:
        query = query.where(func.lower(Game.developer) == filters.developer.lower())
    if filters.publisher:
        query = query.where(func.lower(Game.publisher) == filters.publisher.lower())
    if filters.platform:
        terms = {filters.platform.lower()}
        if filters.platform.lower() == "steam":
            terms.add("pc")
        query = query.where(_json_array_match(Game.platforms, terms, substring=True))
    if filters.player_mode:
        query = query.where(or_(
            _json_array_match(Game.game_modes, {filters.player_mode}),
            _json_array_match(Game.genres, _PLAYER_MODE_GENRE_ALIASES[filters.player_mode]),
        ))
    if filters.playtime_min_hours is not None:
        query = query.where(
            Game.playtime_minutes > 0,
            Game.playtime_minutes >= filters.playtime_min_hours * _MINUTES_PER_HOUR,
        )
    if filters.playtime_max_hours is not None:
        query = query.where(
            Game.playtime_minutes > 0,
            Game.playtime_minutes <= filters.playtime_max_hours * _MINUTES_PER_HOUR,
        )
    if filters.min_ratings is not None:
        query = query.where(_review_count_expression(require_live_score=True) >= filters.min_ratings)
    if filters.max_ratings is not None:
        query = query.where(_review_count_expression(require_live_score=True) <= filters.max_ratings)
    if filters.has_award:
        query = query.where(or_(Game.goty_year.is_not(None), Game.award_count > 0))
    if filters.min_live_sources is not None:
        query = query.where(_live_primary_source_count_expression() >= filters.min_live_sources)
    if filters.require_critic:
        query = query.where(_has_live_critic_expression())
    return query


def _json_array_match(
    column: ColumnElement,
    values: set[str] | frozenset[str],
    *,
    substring: bool = False,
) -> ColumnElement[bool]:
    rows = func.jsonb_array_elements_text(cast(column, JSONB)).table_valued("value")
    stored = func.lower(func.trim(rows.c.value))
    if substring:
        condition = or_(*(func.strpos(stored, value) > 0 for value in values))
    else:
        condition = stored.in_(values)
    return exists(select(1).select_from(rows).where(condition)).correlate(Game)


def _source_score_parts() -> tuple[TableValuedAlias, ColumnElement, ColumnElement[float], ColumnElement[bool]]:
    rows = func.jsonb_array_elements(cast(Game.source_scores, JSONB)).table_valued("value")
    item = cast(rows.c.value, JSONB)
    numeric_score = case(
        (func.jsonb_typeof(item["score"]) == "number", cast(item["score"].astext, Float)),
        else_=0.0,
    )
    valid = and_(
        item["status"].astext == "live",
        numeric_score > 0,
        numeric_score <= _MAX_VALID_SCORE,
    )
    return rows, item, numeric_score, valid


def _source_score_expression(source: str) -> ColumnElement[float]:
    rows, item, numeric_score, valid = _source_score_parts()
    return (
        select(func.coalesce(func.max(case((and_(valid, item["source"].astext == source), numeric_score), else_=0.0)), 0.0))
        .select_from(rows)
        .correlate(Game)
        .scalar_subquery()
    )


def _review_count_expression(*, require_live_score: bool) -> ColumnElement[int]:
    rows, item, _numeric_score, valid = _source_score_parts()
    numeric_reviews = case(
        (func.jsonb_typeof(item["review_count"]) == "number", cast(item["review_count"].astext, BigInteger)),
        else_=0,
    )
    safe_reviews = and_(numeric_reviews >= 0, numeric_reviews <= _MAX_REVIEW_COUNT)
    condition = and_(valid, safe_reviews) if require_live_score else safe_reviews
    return (
        select(func.coalesce(func.sum(case((condition, numeric_reviews), else_=0)), 0))
        .select_from(rows)
        .correlate(Game)
        .scalar_subquery()
    )


def _live_primary_source_count_expression() -> ColumnElement[int]:
    rows, item, _numeric_score, valid = _source_score_parts()
    pc_platform = _json_array_match(Game.platforms, PC_PLATFORM_KEYS)
    applicable_source = or_(
        item["source"].astext.in_(PRIMARY_SOURCES - {"Steam"}),
        and_(item["source"].astext == "Steam", pc_platform),
    )
    return (
        select(func.coalesce(func.sum(case((and_(valid, applicable_source), 1), else_=0)), 0))
        .select_from(rows)
        .correlate(Game)
        .scalar_subquery()
    )


def _has_live_critic_expression() -> ColumnElement[bool]:
    rows, item, _numeric_score, valid = _source_score_parts()
    return exists(
        select(1).select_from(rows).where(and_(valid, item["source"].astext.in_(CRITIC_SOURCES)))
    ).correlate(Game)


def json_array_values_statement(column: ColumnElement) -> Select[tuple[str]]:
    """Distinct, trimmed, sorted values of a JSON array column across all games."""
    values = func.jsonb_array_elements_text(cast(column, JSONB)).table_valued("value").lateral()
    trimmed = func.trim(values.c.value).label("value")
    return (
        select(trimmed)
        .distinct()
        .select_from(Game)
        .join(values, true())
        .where(Game.content_type == "game", trimmed != "")
        .order_by(trimmed)
    )


def build_platform_filters(platforms: set[str]) -> set[str]:
    """Add umbrella facet entries (Steam, PlayStation, Xbox, Nintendo) over raw platform names."""
    filters = set(platforms)
    if any(p in platforms for p in ("PC", "Steam")):
        filters.add("Steam")
    if any("PlayStation" in p for p in platforms):
        filters.add("PlayStation")
    if any("Xbox" in p for p in platforms):
        filters.add("Xbox")
    if any(p in platforms for p in ("Nintendo Switch", "Nintendo", "Wii", "Wii U")):
        filters.add("Nintendo")
    return filters
