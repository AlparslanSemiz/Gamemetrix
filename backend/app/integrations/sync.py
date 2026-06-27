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
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Game
from .igdb import get_igdb_score
from .opencritic import get_opencritic_score
from .rawg_score import get_rawg_metacritic_score
from .steam import extract_steam_app_id, get_steam_score
from .types import ExternalScore


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

# Bayesian prior vote counts per source (keep in sync with source_registry.py).
PRIOR_VOTE_COUNTS: dict[str, int] = {
    "Metacritic": 10,
    "OpenCritic": 10,
    "IGDB": 15,
    "Steam": 800,
    "RAWG": 150,
    "SteamSpy": 400,
    "CheapShark": 40,
    "FreeToGame": 30,
}

GLOBAL_PRIOR_SCORE = 70.0

PRIMARY_RATING_SOURCES = ("Metacritic", "OpenCritic", "IGDB", "Steam")
CRITIC_RATING_SOURCES = {"Metacritic", "OpenCritic"}
USER_RATING_SOURCES = {"IGDB", "Steam"}
HELPER_RATING_SOURCES = {"RAWG", "SteamSpy", "CheapShark", "FreeToGame"}
CACHE_TTL = timedelta(hours=24)


# ── Score serialization ────────────────────────────────────────────────────────


def _score_to_dict(score: ExternalScore) -> dict[str, str | float | int]:
    payload: dict[str, str | float | int] = {
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
    current: list[dict[str, str | float | int]],
    fresh: list[ExternalScore],
) -> list[dict[str, str | float | int]]:
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


# ── Bayesian scoring ───────────────────────────────────────────────────────────


def calculate_metrix_score(source_scores: list[dict[str, str | float | int]]) -> float:
    """
    Compute the Metrix score using Bayesian reliability weighting.

    Each source score is shrunk toward GLOBAL_PRIOR_SCORE (70) based on how far
    its review count is below the source's PRIOR_VOTE_COUNTS threshold.
    This prevents 3 critics averaging 100 from outranking 10 000 users averaging 95.
    """
    usable = [s for s in source_scores if s.get("status") == "live" and float(s.get("score", 0)) > 0]
    primary = [s for s in usable if str(s.get("source")) in PRIMARY_RATING_SOURCES]
    scoring = primary or usable
    if not scoring:
        return 0.0

    weighted_total = 0.0
    total_weight = 0.0
    evidence_total = 0.0

    for s in scoring:
        value = float(s.get("score", 0))
        status = str(s.get("status", "mock"))
        if status == "unavailable" or value <= 0:
            continue

        source = str(s.get("source", ""))
        base_weight = SOURCE_WEIGHTS.get(source, 0.05)
        review_count = int(s.get("review_count", 0))

        adjusted, reliability = _bayesian_adjust(value, status, source, review_count)

        effective_weight = base_weight * reliability
        weighted_total += adjusted * effective_weight
        total_weight += effective_weight
        evidence_total += base_weight * reliability

    if total_weight == 0:
        return 0.0

    source_avg = weighted_total / total_weight
    confidence = _confidence(scoring, primary, evidence_total)
    return round(source_avg * confidence + GLOBAL_PRIOR_SCORE * (1 - confidence), 1)


def _bayesian_adjust(
    value: float,
    status: str,
    source: str,
    review_count: int,
) -> tuple[float, float]:
    if review_count > 0 and status == "live":
        prior = PRIOR_VOTE_COUNTS.get(source, 20)
        adjusted = (GLOBAL_PRIOR_SCORE * prior + value * review_count) / (prior + review_count)
        reliability = min(1.0, review_count / prior)
    elif status == "live":
        adjusted = value
        reliability = 0.92 if source in CRITIC_RATING_SOURCES else 0.78
    else:
        adjusted = value
        reliability = 0.5
    return adjusted, reliability


def _confidence(
    scoring: list[dict],
    primary: list[dict],
    evidence_total: float,
) -> float:
    available_weight = sum(SOURCE_WEIGHTS.get(str(s.get("source", "")), 0.05) for s in scoring)
    if primary:
        universe = sum(SOURCE_WEIGHTS[src] for src in PRIMARY_RATING_SOURCES)
        coverage = min(1.0, available_weight / universe)
        evidence = min(1.0, evidence_total / max(available_weight, 0.01))
        return min(1.0, 0.15 + 0.35 * coverage + 0.50 * evidence)
    else:
        universe = sum(SOURCE_WEIGHTS.get(src, 0) for src in HELPER_RATING_SOURCES)
        coverage = min(1.0, available_weight / max(universe, 0.01))
        evidence = min(1.0, evidence_total / max(available_weight, 0.01))
        return min(0.45, 0.10 + 0.30 * coverage + 0.30 * evidence)


# ── Derived score helpers ──────────────────────────────────────────────────────


def _weighted_source_average(
    source_scores: list[dict[str, str | float | int]],
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
    source_scores: list[dict[str, str | float | int]],
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
        tasks.append(
            _resolve_score(
                "Steam",
                _cached_score(game.source_scores, "Steam"),
                lambda: get_steam_score(
                    game.slug,
                    game.title,
                    steam_app_id=extract_steam_app_id(game.slug, game.cover_url),
                ),
            )
        )
    return tasks


def _update_derived_scores(game: Game, fresh_scores: list[ExternalScore]) -> None:
    for score in fresh_scores:
        if score.source == "Metacritic" and score.status == "live" and score.score > 0:
            game.metacritic_score = round(score.score)
            break

    live = [s for s in game.source_scores if s.get("status") == "live" and float(s.get("score", 0)) > 0]
    if live:
        critic = _weighted_source_average(game.source_scores, CRITIC_RATING_SOURCES)
        user = _weighted_source_average(game.source_scores, USER_RATING_SOURCES)
        if critic > 0:
            game.critic_score = critic
        if user > 0:
            game.user_score = user


async def refresh_game_sources(db: Session, game: Game) -> Game:
    fresh_scores = await asyncio.gather(*_build_fetch_tasks(game))

    from ..services.metadata import enrich_game_summary, fix_game_year
    await asyncio.gather(fix_game_year(game), enrich_game_summary(game))

    game.source_scores = _merge_source_scores(game.source_scores, list(fresh_scores))
    game.metrix_score = calculate_metrix_score(game.source_scores)
    game.ratings_refreshed_at = datetime.now(UTC)
    _update_derived_scores(game, list(fresh_scores))

    db.add(game)
    db.commit()
    db.refresh(game)
    return game
