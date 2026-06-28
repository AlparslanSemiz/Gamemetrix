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
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

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
    "RAWG": 0.04,
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

# Equal-weight scoring: 4 primary slots; RAWG fills at lower weight when a primary is absent.
# SteamSpy, CheapShark, FreeToGame are support sources — never enter the score.
_SCORE_PRIMARIES = ("Metacritic", "OpenCritic", "Steam", "IGDB")
_SCORE_EXTRAS = ("RAWG",)
_SCORE_BASELINE = 70.0

# ── Rank score constants ────────────────────────────────────────────────────────
_RANK_GLOBAL_MEAN = 70.0  # shrinkage target: neutral baseline
_RATING_SRC  = frozenset({"Metacritic", "OpenCritic", "Steam", "IGDB", "RAWG"})
_CRITIC_SRC  = frozenset({"Metacritic", "OpenCritic"})
_USER_SRC    = frozenset({"Steam", "IGDB"})


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
    Reliability-adjusted weighted average of up to 4 sources.

    Primaries: Metacritic, OpenCritic, Steam, IGDB (each defaults to weight 1.0 = 25%).
    Any missing primary slot is filled by the next available extra source.
    Weights are configurable via SCORE_WEIGHT_<SOURCE> env vars (relative, not absolute).
    Sparse source coverage shrinks high scores toward a neutral baseline and applies a
    small uncertainty penalty, so a 95 from one source cannot rank like a 95 from four.
    """
    cfg = get_settings()
    weights: dict[str, float] = {
        "Metacritic": cfg.SCORE_WEIGHT_METACRITIC,
        "OpenCritic": cfg.SCORE_WEIGHT_OPENCRITIC,
        "Steam":      cfg.SCORE_WEIGHT_STEAM,
        "IGDB":       cfg.SCORE_WEIGHT_IGDB,
        "RAWG":       cfg.SCORE_WEIGHT_RAWG,
        "SteamSpy":   cfg.SCORE_WEIGHT_STEAMSPY,
        "CheapShark": cfg.SCORE_WEIGHT_CHEAPSHARK,
        "FreeToGame": cfg.SCORE_WEIGHT_FREETOGAME,
    }
    live = {
        str(s.get("source")): float(s.get("score", 0))
        for s in source_scores
        if s.get("status") == "live" and float(s.get("score", 0)) > 0
    }
    selected: list[tuple[str, float]] = [(src, live[src]) for src in _SCORE_PRIMARIES if src in live]
    needed = 4 - len(selected)
    for src in _SCORE_EXTRAS:
        if needed <= 0:
            break
        if src in live:
            selected.append((src, live[src]))
            needed -= 1
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
    has_rawg_fallback = "RAWG" in selected_sources
    has_critic = bool(selected_sources & _CRITIC_SRC)
    has_user = bool(selected_sources & _USER_SRC)
    total_reviews = sum(
        int(s.get("review_count", 0))
        for s in source_scores
        if s.get("status") == "live" and str(s.get("source")) in _RATING_SRC
    )

    if primary_count >= 4:
        coverage_factor = 1.00
        max_reliability = 1.00
    elif primary_count == 3 and has_rawg_fallback:
        coverage_factor = 0.93
        max_reliability = 0.965
    elif primary_count == 3:
        coverage_factor = 0.90
        max_reliability = 0.94
    elif primary_count == 2 and has_rawg_fallback:
        coverage_factor = 0.82
        max_reliability = 0.87
    elif primary_count == 2:
        coverage_factor = 0.78
        max_reliability = 0.84
    elif primary_count == 1 and has_rawg_fallback:
        coverage_factor = 0.66
        max_reliability = 0.72
    elif primary_count == 1:
        coverage_factor = 0.62
        max_reliability = 0.68
    elif has_rawg_fallback:
        coverage_factor = 0.46
        max_reliability = 0.50
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

    if selected_sources == {"RAWG"}:
        return 0.46

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
        if s.get("status") != "live" or float(s.get("score", 0)) <= 0:
            continue
        weight = SOURCE_WEIGHTS.get(source, 0.05)
        weighted_total += float(s.get("score", 0)) * weight
        total_weight += weight
    return round(weighted_total / total_weight, 1) if total_weight else 0.0


# ── Cache helpers ──────────────────────────────────────────────────────────────


def _cached_score(
    source_scores: list[dict[str, object]],
    source_name: str,
) -> ExternalScore | None:
    for s in source_scores:
        if s.get("source") != source_name:
            continue
        refreshed_at = s.get("refreshed_at")
        if not isinstance(refreshed_at, str):
            continue
        try:
            refreshed_time = datetime.fromisoformat(refreshed_at)
        except ValueError:
            continue
        if datetime.now(UTC) - refreshed_time <= CACHE_TTL:
            return ExternalScore(
                source=source_name,
                score=float(s.get("score", 0)),
                scale=int(s.get("scale", 100)),
                status=str(s.get("status", "live")),  # type: ignore[arg-type]
                detail=str(s.get("detail", "Cached score")),
                review_count=int(s.get("review_count", 0)),
            )
    return None


def game_needs_rating_refresh(game: Game, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    if game.ratings_refreshed_at is None:
        return True
    refreshed_at = game.ratings_refreshed_at
    if refreshed_at.tzinfo is None:
        refreshed_at = refreshed_at.replace(tzinfo=UTC)
    if now - refreshed_at >= CACHE_TTL:
        return True
    known = {str(s.get("source")) for s in game.source_scores}
    return any(src not in known for src in game.applicable_primary_sources)


# ── Fetch orchestration ────────────────────────────────────────────────────────


async def _resolve_score(
    source: str,
    cached: ExternalScore | None,
    fetch: Callable[[], Awaitable[ExternalScore]],
) -> ExternalScore:
    if cached:
        return cached
    if not await get_rate_limiter().acquire(source):
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
            detail=f"{source} request failed: {error}",
        )


def _build_fetch_tasks(game: Game) -> list[Awaitable[ExternalScore]]:
    tasks: list[Awaitable[ExternalScore]] = [
        _resolve_score(
            "Metacritic",
            _cached_score(game.source_scores, "Metacritic"),
            lambda: get_rawg_metacritic_score(game.title, cached_value=game.metacritic_score),
        ),
        _resolve_score(
            "OpenCritic",
            _cached_score(game.source_scores, "OpenCritic"),
            lambda: get_opencritic_score(game.title),
        ),
        _resolve_score(
            "IGDB",
            _cached_score(game.source_scores, "IGDB"),
            lambda: get_igdb_score(game.title),
        ),
    ]
    if game.is_pc_applicable:
        app_id = extract_steam_app_id(game.slug, game.cover_url)
        tasks.append(
            _resolve_score(
                "Steam",
                _cached_score(game.source_scores, "Steam"),
                lambda: get_steam_score(game.slug, game.title, steam_app_id=app_id),
            )
        )
        if app_id is not None:
            tasks.append(
                _resolve_score(
                    "SteamSpy",
                    _cached_score(game.source_scores, "SteamSpy"),
                    lambda: get_steamspy_score(app_id),
                )
            )
    live_primary = {
        str(s.get("source"))
        for s in game.source_scores
        if s.get("status") == "live"
        and float(s.get("score", 0) or 0) > 0
        and str(s.get("source")) in game.applicable_primary_sources
    }
    if len(live_primary) < len(game.applicable_primary_sources):
        tasks.append(
            _resolve_score(
                "RAWG",
                _cached_score(game.source_scores, "RAWG"),
                lambda: get_rawg_rating_score(game.title),
            )
        )
    return tasks


def _live_rating_entries(game: Game) -> list[dict[str, object]]:
    return [
        s for s in game.source_scores
        if s.get("status") == "live"
        and float(s.get("score", 0)) > 0
        and str(s.get("source")) in _RATING_SRC
    ]


def _confidence_factor(game: Game) -> float:
    """
    Returns 0.0–1.0. Drives how much rank_score equals metrix_score.
    1.0 = full confidence (both critic & user, high volume).
    0.0 = no rating data (catalog only).

    Inputs considered: applicable primary counts, critic/user balance,
    review volume, and whether only a secondary source (RAWG) is present.
    """
    live = _live_rating_entries(game)
    if not live:
        return 0.0

    applicable: frozenset[str] = game.applicable_primary_sources
    live_srcs = {str(s.get("source")) for s in live}
    live_primary = live_srcs & applicable
    live_critic = live_primary & _CRITIC_SRC
    live_user   = live_primary & _USER_SRC

    n_primary = len(live_primary)
    n_critic  = len(live_critic)
    n_user    = len(live_user)

    total_reviews  = sum(int(s.get("review_count", 0)) for s in live)
    critic_reviews = sum(
        int(s.get("review_count", 0)) for s in live
        if str(s.get("source")) in _CRITIC_SRC
    )
    user_reviews = sum(
        int(s.get("review_count", 0)) for s in live
        if str(s.get("source")) in _USER_SRC
    )

    # No applicable primary → secondary-only (RAWG)
    if n_primary == 0:
        return 0.48 if total_reviews >= 10_000 else 0.40

    # Both critic AND user coverage
    if n_critic >= 1 and n_user >= 1:
        if n_primary >= 3 and total_reviews >= 500:
            return 1.00
        if n_primary >= 2 and total_reviews >= 100:
            return 0.92
        return 0.85

    # Critic-only
    if n_critic >= 1:
        if n_critic >= 2:
            return 0.85 if critic_reviews >= 50 else 0.80
        if critic_reviews >= 100:
            return 0.80
        if critic_reviews >= 30:
            return 0.74
        return 0.68

    # User-only
    if n_user >= 2:
        return 0.78 if user_reviews >= 50_000 else 0.72
    if n_user == 1:
        src = next(iter(live_user))
        if src == "Steam":
            if user_reviews >= 500_000: return 0.75
            if user_reviews >= 100_000: return 0.70
            if user_reviews >=  25_000: return 0.63
            if user_reviews >=   5_000: return 0.57
            return 0.50
        # IGDB community aggregate
        return 0.62 if user_reviews >= 500 else 0.54

    return 0.45


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
    """Public — called from sync cycle and main.py startup recomputation."""
    factor     = _confidence_factor(game)
    rank_score = round(_RANK_GLOBAL_MEAN + (game.metrix_score - _RANK_GLOBAL_MEAN) * factor, 1)
    is_rankable, reason = _is_rankable_and_reason(game)
    return rank_score, is_rankable, reason


def _update_derived_scores(game: Game, fresh_scores: list[ExternalScore]) -> None:
    for score in fresh_scores:
        if score.source == "Metacritic" and score.status == "live" and score.score > 0:
            game.metacritic_score = round(score.score)
            break

    live = [s for s in game.source_scores if s.get("status") == "live" and float(s.get("score", 0)) > 0]
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
        scores.append(ExternalScore(
            source=source,
            score=float(row.get("score", 0) or 0),
            scale=int(row.get("scale", 100) or 100),
            status=str(row.get("status", "live")),  # type: ignore[arg-type]
            detail=str(row.get("detail", "")) or None,
            review_count=int(row.get("review_count", 0) or 0),
            raw={"source_score": row},
        ))
    if not scores:
        return 0
    _persist_source_records(db, game, scores)
    return len(scores)


async def refresh_game_sources(db: Session, game: Game) -> Game:
    fresh_scores = await asyncio.gather(*_build_fetch_tasks(game))

    from ..services.metadata import enrich_game_summary, fix_game_year
    await asyncio.gather(fix_game_year(game), enrich_game_summary(game))

    game.source_scores = _merge_source_scores(game.source_scores, list(fresh_scores))
    game.metrix_score = calculate_metrix_score(game.source_scores)
    game.ratings_refreshed_at = datetime.now(UTC)
    _update_derived_scores(game, list(fresh_scores))
    _persist_source_records(db, game, list(fresh_scores))

    db.add(game)
    db.commit()
    db.refresh(game)
    return game
