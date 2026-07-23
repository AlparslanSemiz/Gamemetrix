"""
Scoring engine and game refresh orchestration.

Public API:
  calculate_metrix_score(source_scores)  -> float
  game_needs_rating_refresh(game, now)   -> bool
  refresh_game_sources(db, game)         -> Awaitable[Game]

Internal helpers (prefixed _):
  _score_to_dict, _merge_source_scores, _cached_score,
  _build_fetch_tasks, _update_derived_scores, _weighted_source_average
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from math import isfinite

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ExternalId, Game, RatingSnapshot, SourceSnapshot
from .igdb import get_igdb_score
from .opencritic import get_opencritic_score
from .rate_limiter import get_rate_limiter
from .rawg_score import get_rawg_metacritic_score, get_rawg_rating_score
from .steam import extract_steam_app_id, get_steam_score
from .steamspy import get_steamspy_score
from .types import ExternalScore


log = logging.getLogger(__name__)


# Source weights reflect editorial quality and signal reliability.
# Keep in sync with prior_count values in source_registry.py.
SOURCE_WEIGHTS: dict[str, float] = {
    "Metacritic": 0.32,
    "OpenCritic": 0.28,
    "Steam": 0.25,
    "IGDB": 0.15,
    "RAWG": 0.0,
    "SteamSpy": 0.03,
    "CheapShark": 0.02,
    "FreeToGame": 0.01,
}

SOURCE_ORDER: dict[str, int] = {
    "Metacritic": 0,
    "OpenCritic": 1,
    "IGDB": 2,
    "Steam": 3,
    "RAWG": 4,
    "SteamSpy": 5,
    "CheapShark": 6,
    "FreeToGame": 7,
}

PRIMARY_RATING_SOURCES = ("Metacritic", "OpenCritic", "IGDB", "Steam")
CRITIC_RATING_SOURCES = {"Metacritic", "OpenCritic"}
USER_RATING_SOURCES = {"IGDB", "Steam"}
CACHE_TTL = timedelta(hours=24)
# Fully-populated games only need an occasional re-verify, so they stop competing
# with the incomplete tail for daily API budget.
DATA_COMPLETE_TTL = timedelta(days=30)
RAWG_CACHE_TTL = timedelta(days=30)
_DEFAULT_BUDGET_SOURCE = object()

# Four named primary slots. RAWG and support sources never enter the score.
_SCORE_PRIMARIES = ("Metacritic", "OpenCritic", "Steam", "IGDB")
_SCORE_BASELINE = 70.0

# ── Rank score constants ────────────────────────────────────────────────────────
_RATING_SRC  = frozenset({"Metacritic", "OpenCritic", "Steam", "IGDB"})
_CRITIC_SRC  = frozenset({"Metacritic", "OpenCritic"})
_USER_SRC    = frozenset({"Steam", "IGDB"})


def _score_value(row: Mapping[str, object]) -> float | None:
    try:
        value = float(row.get("score", 0) or 0)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) and 0 < value <= 100 else None


def _review_count(row: Mapping[str, object]) -> int:
    try:
        value = int(row.get("review_count", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return value if 0 <= value <= 2_000_000_000 else 0


# ── Score serialization ────────────────────────────────────────────────────────


def _score_to_dict(score: ExternalScore) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": score.source,
        "score": score.score,
        "scale": score.scale,
        "status": score.status,
        "review_count": score.review_count,
        "refreshed_at": datetime.now(UTC).isoformat(),
    }
    if score.detail:
        payload["detail"] = score.detail
    if score.raw:
        payload.update(score.raw)
    return payload


def _merge_source_scores(
    current: list[dict[str, object]],
    fresh: list[ExternalScore],
) -> list[dict[str, object]]:
    by_source = {str(s["source"]): s for s in current}
    for score in fresh:
        existing = by_source.get(score.source)
        existing_status = str(existing.get("status", "")) if existing else ""
        if score.status == "live" or existing is None or existing_status != "live":
            by_source[score.source] = _score_to_dict(score)
    return sorted(
        by_source.values(),
        key=lambda s: SOURCE_ORDER.get(str(s.get("source", "")), 99),
    )


# ── Scoring ────────────────────────────────────────────────────────────────────


def calculate_metrix_score(source_scores: list[dict[str, object]]) -> float:
    """
    Reliability-adjusted weighted average of the four primary sources.

    Primaries: Metacritic, OpenCritic, Steam, IGDB. Admin weights provide the
    editorial baseline and SCORE_WEIGHT_<SOURCE> env values act as relative
    deployment-level multipliers.
    Sparse source coverage shrinks high scores toward a neutral baseline and applies a
    small uncertainty penalty, so a 95 from one source cannot rank like a 95 from four.
    """
    cfg = get_settings()
    modifiers: dict[str, float] = {
        "Metacritic": cfg.SCORE_WEIGHT_METACRITIC,
        "OpenCritic": cfg.SCORE_WEIGHT_OPENCRITIC,
        "Steam": cfg.SCORE_WEIGHT_STEAM,
        "IGDB": cfg.SCORE_WEIGHT_IGDB,
    }
    weights: dict[str, float] = {
        source: max(0.0, SOURCE_WEIGHTS[source] * modifiers[source])
        for source in _SCORE_PRIMARIES
    }
    live = {
        str(s.get("source")): value
        for s in source_scores
        if s.get("status") == "live" and (value := _score_value(s)) is not None
    }
    selected: list[tuple[str, float]] = [(src, live[src]) for src in _SCORE_PRIMARIES if src in live]
    if not selected:
        return 0.0
    total_weight = sum(weights.get(src, 1.0) for src, _ in selected)
    if total_weight == 0:
        return 0.0
    raw_score = sum(weights.get(src, 1.0) * score for src, score in selected) / total_weight
    reliability = _score_reliability_factor(source_scores, selected)
    uncertainty_penalty = (1.0 - reliability) * 6.0
    adjusted = (raw_score * reliability) + (_SCORE_BASELINE * (1.0 - reliability)) - uncertainty_penalty
    return round(max(0.0, min(100.0, adjusted)), 1)


def _score_reliability_factor(
    source_scores: list[dict[str, object]],
    selected: list[tuple[str, float]],
) -> float:
    selected_sources = {source for source, _ in selected}
    primary_count = len(selected_sources & set(_SCORE_PRIMARIES))
    has_critic = bool(selected_sources & _CRITIC_SRC)
    has_user = bool(selected_sources & _USER_SRC)
    total_reviews = sum(
        _review_count(s)
        for s in source_scores
        if s.get("status") == "live" and str(s.get("source")) in _RATING_SRC
    )

    if primary_count >= 4:
        coverage_factor = 1.00
        max_reliability = 1.00
    elif primary_count == 3:
        coverage_factor = 0.90
        max_reliability = 0.94
    elif primary_count == 2:
        coverage_factor = 0.78
        max_reliability = 0.84
    elif primary_count == 1:
        coverage_factor = 0.62
        max_reliability = 0.68
    else:
        coverage_factor = 0.40
        max_reliability = 0.46

    if has_critic and has_user:
        balance_adjust = 0.03
    elif has_critic:
        balance_adjust = -0.04
    elif has_user:
        balance_adjust = -0.06
    else:
        balance_adjust = -0.10

    if total_reviews >= 100_000:
        volume_adjust = 0.04
    elif total_reviews >= 10_000:
        volume_adjust = 0.02
    elif total_reviews >= 500:
        volume_adjust = 0.01
    elif total_reviews == 0:
        volume_adjust = -0.04
    else:
        volume_adjust = -0.02

    return max(0.46, min(max_reliability, coverage_factor + balance_adjust + volume_adjust))


# ── Derived score helpers ──────────────────────────────────────────────────────


def _weighted_source_average(
    source_scores: list[dict[str, object]],
    sources: set[str],
) -> float:
    weighted_total = 0.0
    total_weight = 0.0
    for s in source_scores:
        source = str(s.get("source", ""))
        if source not in sources:
            continue
        score = _score_value(s)
        if s.get("status") != "live" or score is None:
            continue
        weight = SOURCE_WEIGHTS.get(source, 0.05)
        weighted_total += score * weight
        total_weight += weight
    return round(weighted_total / total_weight, 1) if total_weight else 0.0


# ── Cache helpers ──────────────────────────────────────────────────────────────


def _cached_score(
    source_scores: list[dict[str, object]],
    source_name: str,
    ttl: timedelta | None = None,
    *,
    live_only: bool = False,
) -> ExternalScore | None:
    effective_ttl = ttl if ttl is not None else CACHE_TTL
    for s in source_scores:
        if s.get("source") != source_name:
            continue
        refreshed_at = s.get("refreshed_at")
        if not isinstance(refreshed_at, str):
            continue
        status = str(s.get("status", "live"))
        score = _score_value(s)
        if status == "unavailable" and not live_only:
            score = 0.0
        if score is None or (live_only and status != "live"):
            continue
        try:
            refreshed_time = datetime.fromisoformat(refreshed_at)
        except ValueError:
            continue
        if datetime.now(UTC) - refreshed_time <= effective_ttl:
            try:
                return ExternalScore(
                    source=source_name,
                    score=score,
                    scale=int(s.get("scale", 100)),
                    status=status,  # type: ignore[arg-type]
                    detail=str(s.get("detail", "Cached score"))[:1000],
                    review_count=_review_count(s),
                )
            except (TypeError, ValueError, OverflowError):
                continue
    return None


def game_needs_rating_refresh(game: Game, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    if game.ratings_refreshed_at is None:
        return True
    refreshed_at = game.ratings_refreshed_at
    if refreshed_at.tzinfo is None:
        refreshed_at = refreshed_at.replace(tzinfo=UTC)
    ttl = DATA_COMPLETE_TTL if game.data_complete else CACHE_TTL
    if now - refreshed_at >= ttl:
        return True
    live = {
        str(s.get("source"))
        for s in game.source_scores
        if s.get("status") == "live" and _score_value(s) is not None
    }
    return any(src not in live for src in game.applicable_primary_sources)


# ── Fetch orchestration ────────────────────────────────────────────────────────


async def _resolve_score(
    source: str,
    cached: ExternalScore | None,
    fetch: Callable[[], Awaitable[ExternalScore]],
    *,
    budget_source: str | None | object = _DEFAULT_BUDGET_SOURCE,
    required_requests: int | None = None,
) -> ExternalScore:
    if cached:
        return cached
    if budget_source is _DEFAULT_BUDGET_SOURCE:
        budget_source = source
    if budget_source is not None and not _source_configured(source):
        return ExternalScore(
            source=source,
            score=0,
            status="unavailable",
            detail=f"{source} is not configured.",
        )
    if required_requests is None:
        required_requests = 2 if source == "OpenCritic" else 1
    if (
        budget_source is not None
        and get_rate_limiter().remaining(budget_source) < required_requests
    ):
        return ExternalScore(
            source=source,
            score=0,
            status="unavailable",
            detail=f"{source} request budget is too low for a complete lookup.",
        )
    if budget_source is not None and not await get_rate_limiter().acquire(budget_source):
        return ExternalScore(
            source=source,
            score=0,
            status="unavailable",
            detail=f"{source} daily request budget exhausted — will retry in next refresh cycle",
        )
    try:
        return await fetch()
    except Exception as error:
        return ExternalScore(
            source=source,
            score=0,
            status="unavailable",
            detail=f"{source} request failed ({type(error).__name__}).",
        )


def _source_configured(source: str) -> bool:
    cfg = get_settings()
    if source in {"Metacritic", "RAWG"}:
        return cfg.rawg_configured()
    if source == "OpenCritic":
        return cfg.opencritic_configured()
    if source == "IGDB":
        return cfg.igdb_configured()
    return True


def _wants_source(requested: set[str] | None, source: str) -> bool:
    return requested is None or source in requested


def _fetch_cached_score(
    game: Game,
    source: str,
    *,
    force: bool,
    live_only: bool,
    ttl: timedelta | None = None,
) -> ExternalScore | None:
    if force:
        return None
    return _cached_score(game.source_scores, source, ttl, live_only=live_only)


def _numeric_external_id(external_ids: Mapping[str, str], source: str) -> int | None:
    value = external_ids.get(source, "")
    return int(value) if value.isdigit() and int(value) > 0 else None


def _primary_fetch_tasks(
    game: Game,
    external_ids: Mapping[str, str],
    requested: set[str] | None,
    *,
    force: bool,
    live_only_cache: bool,
    release_year: int | None,
) -> list[Awaitable[ExternalScore]]:
    tasks: list[Awaitable[ExternalScore]] = []
    cached = lambda source, ttl=None: _fetch_cached_score(
        game,
        source,
        force=force,
        live_only=live_only_cache,
        ttl=ttl,
    )
    if _wants_source(requested, "Metacritic"):
        tasks.append(_resolve_score(
            "Metacritic",
            cached("Metacritic", RAWG_CACHE_TTL),
            lambda: get_rawg_metacritic_score(
                game.title,
                cached_value=game.metacritic_score,
                release_year=release_year,
            ),
            budget_source=None if game.metacritic_score is not None else "Metacritic",
        ))
    if _wants_source(requested, "OpenCritic"):
        tasks.append(_resolve_score(
            "OpenCritic",
            cached("OpenCritic"),
            lambda: get_opencritic_score(
                game.title,
                release_year=release_year,
                opencritic_id=external_ids.get("OpenCritic"),
            ),
            required_requests=1,
        ))
    if _wants_source(requested, "IGDB"):
        tasks.append(_resolve_score(
            "IGDB",
            cached("IGDB"),
            lambda: get_igdb_score(
                game.title,
                release_year=release_year,
                igdb_id=_numeric_external_id(external_ids, "IGDB"),
            ),
        ))
    return tasks


def _steam_fetch_tasks(
    game: Game,
    external_ids: Mapping[str, str],
    requested: set[str] | None,
    *,
    force: bool,
    include_support: bool,
    live_only_cache: bool,
) -> list[Awaitable[ExternalScore]]:
    if not _wants_source(requested, "Steam"):
        return []
    if not game.is_pc_applicable and requested is None:
        return []
    app_id = _numeric_external_id(external_ids, "Steam") or extract_steam_app_id(
        game.slug,
        game.cover_url,
        game.image_url,
    )
    tasks = [_resolve_score(
        "Steam",
        _fetch_cached_score(game, "Steam", force=force, live_only=live_only_cache),
        lambda: get_steam_score(game.slug, game.title, steam_app_id=app_id),
        required_requests=1 if app_id is not None else 2,
    )]
    if include_support and app_id is not None and _wants_source(requested, "SteamSpy"):
        tasks.append(_resolve_score(
            "SteamSpy",
            _fetch_cached_score(game, "SteamSpy", force=force, live_only=live_only_cache),
            lambda: get_steamspy_score(app_id),
        ))
    return tasks


def _needs_rawg_fallback(game: Game) -> bool:
    live_primary = {
        str(score.get("source"))
        for score in game.source_scores
        if score.get("status") == "live"
        and _score_value(score) is not None
        and str(score.get("source")) in game.applicable_primary_sources
    }
    return len(live_primary) < len(game.applicable_primary_sources)


def _build_fetch_tasks(
    game: Game,
    *,
    external_ids: Mapping[str, str] | None = None,
    sources: Sequence[str] | None = None,
    force: bool = False,
    include_support: bool = True,
    include_rawg_fallback: bool = True,
) -> list[Awaitable[ExternalScore]]:
    requested = set(sources) if sources is not None else None
    live_only_cache = requested is not None
    external_ids = external_ids or {}
    release_year = game.release_year if game.release_year and game.release_year > 1970 else None

    tasks = _primary_fetch_tasks(
        game,
        external_ids,
        requested,
        force=force,
        live_only_cache=live_only_cache,
        release_year=release_year,
    )
    tasks.extend(_steam_fetch_tasks(
        game,
        external_ids,
        requested,
        force=force,
        include_support=include_support,
        live_only_cache=live_only_cache,
    ))
    if (
        include_rawg_fallback
        and _wants_source(requested, "RAWG")
        and _needs_rawg_fallback(game)
    ):
        tasks.append(
            _resolve_score(
                "RAWG",
                _fetch_cached_score(
                    game,
                    "RAWG",
                    force=force,
                    live_only=live_only_cache,
                    ttl=RAWG_CACHE_TTL,
                ),
                lambda: get_rawg_rating_score(game.title, release_year=release_year),
            )
        )
    return tasks


def _live_rating_entries(game: Game) -> list[dict[str, object]]:
    return [
        s for s in game.source_scores
        if s.get("status") == "live"
        and _score_value(s) is not None
        and str(s.get("source")) in _RATING_SRC
    ]


def _is_rankable_and_reason(game: Game) -> tuple[bool, str | None]:
    """
    A game is rankable when it meets any one of:
      1. 2+ applicable primary rating sources with live data
      2. 1 critic source + 1 user source
      3. Award-backed (GOTY or award_count > 0) with at least 1 primary source
    """
    if game.content_type != "game":
        return False, "not_rankable_content_type"

    live = _live_rating_entries(game)
    if not live:
        return False, "catalog_only"

    applicable: frozenset[str] = game.applicable_primary_sources
    live_srcs    = {str(s.get("source")) for s in live}
    live_primary = live_srcs & applicable
    live_critic  = live_primary & _CRITIC_SRC
    live_user    = live_primary & _USER_SRC

    if len(live_primary) >= 2:
        return True, None
    if live_critic and live_user:
        return True, None
    if (game.goty_year or (game.award_count or 0) > 0) and live_primary:
        return True, None

    return False, "insufficient_rating_data"


def compute_rank_fields(game: Game) -> tuple[float, bool, str | None]:
    """Public — called from sync cycle and main.py startup recomputation.

    rank_score mirrors the displayed metrix_score so the default list orders by
    the score shown on each card. metrix_score is already reliability-adjusted in
    calculate_metrix_score, so no second shrinkage is applied here.
    """
    rank_score = round(game.metrix_score, 1)
    is_rankable, reason = _is_rankable_and_reason(game)
    return rank_score, is_rankable, reason


def _update_derived_scores(game: Game, fresh_scores: list[ExternalScore]) -> None:
    for score in fresh_scores:
        if score.source == "Metacritic" and score.status == "live" and score.score > 0:
            game.metacritic_score = round(score.score)
            break

    live = [s for s in game.source_scores if s.get("status") == "live" and _score_value(s) is not None]
    if live:
        critic = _weighted_source_average(game.source_scores, CRITIC_RATING_SOURCES)
        user   = _weighted_source_average(game.source_scores, USER_RATING_SOURCES)
        if critic > 0:
            game.critic_score = critic
        if user > 0:
            game.user_score = user

    rank_score, is_rankable, _ = compute_rank_fields(game)
    game.rank_score  = rank_score
    game.is_rankable = is_rankable


def _external_id_from_score(score: ExternalScore) -> tuple[str, str, str | None, str | None] | None:
    raw = score.raw or {}
    if score.source == "Steam" and raw.get("steam_app_id"):
        app_id = str(raw["steam_app_id"])
        return ("Steam", app_id, None, f"https://store.steampowered.com/app/{app_id}/")
    if score.source == "IGDB" and raw.get("igdb_id"):
        return ("IGDB", str(raw["igdb_id"]), raw.get("igdb_slug"), raw.get("igdb_url"))  # type: ignore[arg-type]
    if score.source == "OpenCritic" and raw.get("opencritic_id"):
        opencritic_id = str(raw["opencritic_id"])
        return ("OpenCritic", opencritic_id, None, f"https://opencritic.com/game/{opencritic_id}/")
    if score.source == "Metacritic" and raw.get("rawg_id"):
        return ("RAWG", str(raw["rawg_id"]), raw.get("rawg_slug"), raw.get("rawg_url"))  # type: ignore[arg-type]
    return None


def _upsert_external_id_from_score(db: Session, game: Game, score: ExternalScore, now: datetime) -> None:
    external = _external_id_from_score(score)
    if external is None:
        return
    source, external_id, external_slug, external_url = external
    existing = db.scalar(
        select(ExternalId).where(
            ExternalId.game_id == game.id,
            ExternalId.source == source,
        )
    )
    if existing:
        existing.external_id = external_id
        existing.external_slug = external_slug
        existing.external_url = external_url
        existing.updated_at = now
        return
    db.add(ExternalId(
        game_id=game.id,
        source=source,
        external_id=external_id,
        external_slug=external_slug,
        external_url=external_url,
        confidence=0.95 if score.status == "live" else 0.6,
        is_primary=True,
        created_at=now,
        updated_at=now,
    ))


def _persist_source_records(db: Session, game: Game, scores: list[ExternalScore]) -> None:
    now = datetime.now(UTC)
    applicable = game.applicable_primary_sources
    for score in scores:
        raw_payload = {
            "source": score.source,
            "status": score.status,
            "score": score.score,
            "scale": score.scale,
            "detail": score.detail,
            "review_count": score.review_count,
            "raw": score.raw or {},
        }
        normalized = round((score.score / score.scale) * 100, 1) if score.scale and score.score > 0 else None
        db.add(RatingSnapshot(
            game_id=game.id,
            source=score.source,
            score=score.score if score.score > 0 else None,
            score_normalized=normalized,
            rating_count=score.review_count,
            review_count=score.review_count,
            critic_count=score.review_count if score.source in CRITIC_RATING_SOURCES else None,
            user_count=score.review_count if score.source in USER_RATING_SOURCES else None,
            is_critic=score.source in CRITIC_RATING_SOURCES,
            is_user=score.source in USER_RATING_SOURCES,
            is_applicable=score.source in applicable or score.source == "RAWG",
            confidence=1.0 if score.status == "live" else 0.0,
            raw_payload=raw_payload,
            fetched_at=now,
            created_at=now,
        ))
        db.add(SourceSnapshot(
            source=score.source,
            endpoint="rating-refresh",
            query=game.title,
            external_id=str((_external_id_from_score(score) or ("", "", None, None))[1] or "") or None,
            status_code=None,
            raw_payload=raw_payload,
            fetched_at=now,
            created_at=now,
        ))
        _upsert_external_id_from_score(db, game, score, now)


def backfill_current_source_records(db: Session, game: Game) -> int:
    """Persist current Game.source_scores into audit tables once per source."""
    scores: list[ExternalScore] = []
    for row in game.source_scores or []:
        source = str(row.get("source", ""))
        if not source:
            continue
        exists = db.scalar(
            select(RatingSnapshot.id)
            .where(RatingSnapshot.game_id == game.id, RatingSnapshot.source == source)
            .limit(1)
        )
        if exists:
            continue
        status = str(row.get("status", "live"))
        score = _score_value(row) or 0.0
        try:
            scores.append(ExternalScore(
                source=source,
                score=score,
                scale=int(row.get("scale", 100) or 100),
                status=status,  # type: ignore[arg-type]
                detail=(str(row.get("detail", "")) or None),
                review_count=_review_count(row),
                raw={"source_score": row},
            ))
        except (TypeError, ValueError, OverflowError):
            continue
    if not scores:
        return 0
    _persist_source_records(db, game, scores)
    return len(scores)


async def refresh_game_sources(
    db: Session,
    game: Game,
    *,
    sources: Sequence[str] | None = None,
    force: bool = False,
    include_support: bool = True,
    include_rawg_fallback: bool = True,
    refresh_metadata: bool = True,
) -> Game:
    external_rows = db.scalars(
        select(ExternalId)
        .where(
            ExternalId.game_id == game.id,
            ExternalId.is_primary.is_(True),
            ExternalId.confidence >= 0.8,
        )
        .order_by(ExternalId.confidence.desc(), ExternalId.updated_at.desc())
    ).all()
    external_ids: dict[str, str] = {}
    for row in external_rows:
        external_ids.setdefault(row.source, row.external_id)

    fresh_scores = await asyncio.gather(*_build_fetch_tasks(
        game,
        external_ids=external_ids,
        sources=sources,
        force=force,
        include_support=include_support,
        include_rawg_fallback=include_rawg_fallback,
    ))

    if refresh_metadata:
        from ..services.metadata import enrich_game_summary, fix_game_year
        await asyncio.gather(fix_game_year(game), enrich_game_summary(game))

    game.source_scores = _merge_source_scores(game.source_scores, list(fresh_scores))
    game.metrix_score = calculate_metrix_score(game.source_scores)
    game.ratings_refreshed_at = datetime.now(UTC)
    _update_derived_scores(game, list(fresh_scores))
    _persist_source_records(db, game, list(fresh_scores))
    from ..services.seo import refresh_game_seo_state
    refresh_game_seo_state(game, content_updated=True)
    from ..services.completeness import refresh_data_complete
    refresh_data_complete(game)

    db.add(game)
    db.commit()
    db.refresh(game)
    return game
