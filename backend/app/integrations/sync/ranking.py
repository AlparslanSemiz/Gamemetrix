"""Whether a game qualifies for ranked lists, and its derived display scores."""

from ...models import Game
from ..types import ExternalScore
from .constants import CRITIC_RATING_SOURCES, RATING_SRC, USER_RATING_SOURCES
from .scoring import weighted_source_average
from .values import score_value

_MIN_PRIMARY_SOURCES_FOR_RANK = 2


def _live_rating_entries(game: Game) -> list[dict[str, object]]:
    return [
        s for s in game.source_scores
        if s.get("status") == "live"
        and score_value(s) is not None
        and str(s.get("source")) in RATING_SRC
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

    live_sources = {str(s.get("source")) for s in live}
    live_primary = live_sources & game.applicable_primary_sources
    live_critic = live_primary & CRITIC_RATING_SOURCES
    live_user = live_primary & USER_RATING_SOURCES

    if len(live_primary) >= _MIN_PRIMARY_SOURCES_FOR_RANK:
        return True, None
    if live_critic and live_user:
        return True, None
    if (game.goty_year or (game.award_count or 0) > 0) and live_primary:
        return True, None
    return False, "insufficient_rating_data"


def compute_rank_fields(game: Game) -> tuple[float, bool, str | None]:
    """Public — called from the sync cycle and main.py startup recomputation.

    rank_score mirrors the displayed metrix_score so the default list orders by
    the score shown on each card. metrix_score is already reliability-adjusted in
    calculate_metrix_score, so no second shrinkage is applied here.
    """
    rank_score = round(game.metrix_score, 1)
    is_rankable, reason = _is_rankable_and_reason(game)
    return rank_score, is_rankable, reason


def update_derived_scores(game: Game, fresh_scores: list[ExternalScore]) -> None:
    _apply_metacritic_score(game, fresh_scores)
    _apply_critic_user_averages(game)
    rank_score, is_rankable, _ = compute_rank_fields(game)
    game.rank_score = rank_score
    game.is_rankable = is_rankable


def _apply_metacritic_score(game: Game, fresh_scores: list[ExternalScore]) -> None:
    for score in fresh_scores:
        if score.source == "Metacritic" and score.status == "live" and score.score > 0:
            game.metacritic_score = round(score.score)
            return


def _apply_critic_user_averages(game: Game) -> None:
    has_live = any(
        s.get("status") == "live" and score_value(s) is not None for s in game.source_scores
    )
    if not has_live:
        return
    critic = weighted_source_average(game.source_scores, CRITIC_RATING_SOURCES)
    user = weighted_source_average(game.source_scores, USER_RATING_SOURCES)
    if critic > 0:
        game.critic_score = critic
    if user > 0:
        game.user_score = user
