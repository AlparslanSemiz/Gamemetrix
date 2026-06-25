from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Game
from .igdb import get_igdb_score
from .opencritic import get_opencritic_score
from .steam import get_steam_score
from .types import ExternalScore


# Source weights reflect editorial quality and signal reliability.
# Critic sources (Metacritic, OpenCritic, IGDB) are authoritative but need
# sufficient review volume; user sources (Steam) carry high volume signal.
SOURCE_WEIGHTS: dict[str, float] = {
    "Metacritic": 0.30,
    "OpenCritic": 0.30,
    "IGDB": 0.15,
    "Steam": 0.15,
    "RAWG": 0.05,
    "SteamSpy": 0.08,
    "CheapShark": 0.04,
    "FreeToGame": 0.03,
}

# Bayesian prior vote counts per source.
# A game needs at least this many reviews before its score is trusted at face value.
# Critic sources: low threshold (10–15 critics = enough signal).
# User sources: high threshold (thousands of users needed for stability).
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

# Global prior score: the expected score for a game with zero reviews.
# Set conservatively so low-sample scores are pulled toward average, not toward 100.
GLOBAL_PRIOR_SCORE = 70.0

CACHE_TTL = timedelta(hours=12)


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
    return payload


def _merge_source_scores(
    current_scores: list[dict[str, str | float | int]],
    fresh_scores: list[ExternalScore],
) -> list[dict[str, str | float | int]]:
    by_source = {str(score["source"]): score for score in current_scores}

    for score in fresh_scores:
        if score.status == "live":
            by_source[score.source] = _score_to_dict(score)
        elif score.source not in by_source:
            by_source[score.source] = _score_to_dict(score)

    return list(by_source.values())


def calculate_metrix_score(source_scores: list[dict[str, str | float | int]]) -> float:
    """
    Compute the Metrix score using Bayesian reliability weighting.

    For each source with a known review_count, the raw score is pulled toward
    GLOBAL_PRIOR_SCORE in proportion to how far the sample size is below the
    source's PRIOR_VOTE_COUNTS threshold. This prevents a game reviewed by
    3 critics (even if all gave 100) from outranking a game with 10,000
    user reviews averaging 95.

    Sources without review_count (imported/mock data) contribute at reduced
    weight (70% for live data, 50% for mock) so they don't dominate over
    high-confidence live sources.
    """
    weighted_total = 0.0
    total_weight = 0.0

    for score in source_scores:
        value = float(score.get("score", 0))
        status = str(score.get("status", "mock"))

        if status == "unavailable" or value <= 0:
            continue

        source = str(score.get("source", ""))
        base_weight = SOURCE_WEIGHTS.get(source, 0.05)
        review_count = int(score.get("review_count", 0))

        if review_count > 0 and status == "live":
            prior_count = PRIOR_VOTE_COUNTS.get(source, 20)
            # Bayesian mean: adjusts toward GLOBAL_PRIOR_SCORE when sample is small.
            # As review_count → ∞, adjusted_score → value.
            adjusted = (GLOBAL_PRIOR_SCORE * prior_count + value * review_count) / (
                prior_count + review_count
            )
            reliability = 1.0
        elif status == "live":
            # Live data but review_count unknown — trust it but at partial weight.
            adjusted = value
            reliability = 0.7
        else:
            # Mock / imported without live verification.
            adjusted = value
            reliability = 0.5

        effective_weight = base_weight * reliability
        weighted_total += adjusted * effective_weight
        total_weight += effective_weight

    if total_weight == 0:
        return 0.0

    return round(weighted_total / total_weight, 1)


def _cached_live_score(
    source_scores: list[dict[str, str | float | int]],
    source_name: str,
) -> ExternalScore | None:
    for score in source_scores:
        if score.get("source") != source_name or score.get("status") != "live":
            continue

        refreshed_at = score.get("refreshed_at")
        if not isinstance(refreshed_at, str):
            continue

        try:
            refreshed_time = datetime.fromisoformat(refreshed_at)
        except ValueError:
            continue

        if datetime.now(UTC) - refreshed_time <= CACHE_TTL:
            return ExternalScore(
                source=source_name,
                score=float(score.get("score", 0)),
                scale=int(score.get("scale", 100)),
                status="live",
                detail=str(score.get("detail", "Cached score")),
                review_count=int(score.get("review_count", 0)),
            )

    return None


async def refresh_game_sources(db: Session, game: Game) -> Game:
    cached_steam = _cached_live_score(game.source_scores, "Steam")
    cached_oc = _cached_live_score(game.source_scores, "OpenCritic")

    steam_score = cached_steam or await get_steam_score(game.slug, game.title)
    igdb_score = await get_igdb_score(game.title)
    oc_score = cached_oc or await get_opencritic_score(game.title)

    fresh_scores: list[ExternalScore] = [steam_score, igdb_score, oc_score]

    game.source_scores = _merge_source_scores(game.source_scores, fresh_scores)
    game.metrix_score = calculate_metrix_score(game.source_scores)

    live_scores = [
        score
        for score in game.source_scores
        if score.get("status") == "live" and float(score.get("score", 0)) > 0
    ]
    if live_scores:
        game.user_score = round(
            sum(float(s["score"]) for s in live_scores) / len(live_scores),
            1,
        )

    db.add(game)
    db.commit()
    db.refresh(game)
    return game
