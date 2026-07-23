"""Ordering scored candidates into the list the detail page shows.

Candidates are admitted in widening tiers — strict gate first, then loosened
overlap rules — until enough results exist, then capped per franchise so one
series cannot fill the row.
"""

from dataclasses import dataclass

from ...models import Game
from .gates import passes_similarity_gate
from .profiles import (
    has_specialized_signals,
    is_same_developer,
    is_same_series,
    shared_meaningful_genre_count,
    shared_specialized_signal_count,
)
from .scoring import similarity_score
from .signals import meaningful_genres, series_key_for_title

SIMILAR_MIN_SCORE = 42
SIMILAR_FALLBACK_MIN_SCORE = 24
SIMILAR_MIN_RESULTS = 6
SIMILAR_MAX_SAME_SERIES = 3

_ScoredGame = tuple[Game, float]


@dataclass(frozen=True)
class _SourceProfile:
    game: Game
    is_specialized: bool
    has_genres: bool

    @classmethod
    def build(cls, game: Game) -> "_SourceProfile":
        return cls(
            game=game,
            is_specialized=has_specialized_signals(game),
            has_genres=bool(meaningful_genres(game)),
        )

    @property
    def min_score(self) -> float:
        return SIMILAR_MIN_SCORE if self.is_specialized else SIMILAR_FALLBACK_MIN_SCORE

    def shares_content(self, candidate: Game) -> bool:
        return (
            shared_meaningful_genre_count(self.game, candidate) > 0
            or shared_specialized_signal_count(self.game, candidate) > 0
        )

    def is_related(self, candidate: Game) -> bool:
        return is_same_series(self.game, candidate) or is_same_developer(self.game, candidate)


def rank_similar_games(source: Game, candidates: list[Game], display_limit: int = 10) -> list[Game]:
    profile = _SourceProfile.build(source)
    ranked = _rank_candidates(source, candidates)

    selected: list[Game] = []
    for build_tier in (_strict_tier, _overlap_tier, _closest_tier):
        chosen = {game.slug for game in selected}
        addition = [game for game in build_tier(profile, ranked) if game.slug not in chosen]
        selected = _diversify(source, selected + addition, display_limit)
        if len(selected) >= SIMILAR_MIN_RESULTS:
            break
    return selected


def _rank_candidates(source: Game, candidates: list[Game]) -> list[_ScoredGame]:
    by_slug: dict[str, Game] = {
        candidate.slug: candidate
        for candidate in candidates
        if candidate.slug != source.slug and candidate.content_type == "game"
    }
    return sorted(
        ((c, similarity_score(source, c)) for c in by_slug.values()),
        key=lambda item: (item[1], item[0].rank_score),
        reverse=True,
    )


def _strict_tier(profile: _SourceProfile, ranked: list[_ScoredGame]) -> list[Game]:
    """Candidates that clear the gate, plus a looser pass for genre/series overlap."""
    primary = [game for game, score in ranked if _passes_primary(profile, game, score)]
    primary_slugs = {game.slug for game in primary}
    fallback = [
        game
        for game, score in ranked
        if game.slug not in primary_slugs
        and score >= SIMILAR_FALLBACK_MIN_SCORE
        and (
            not profile.has_genres
            or profile.shares_content(game)
            or is_same_series(profile.game, game)
        )
    ]
    return primary + fallback


def _passes_primary(profile: _SourceProfile, candidate: Game, score: float) -> bool:
    if score < profile.min_score or not passes_similarity_gate(profile.game, candidate):
        return False
    if not profile.has_genres:
        return True
    return profile.shares_content(candidate) or profile.is_related(candidate)


def _overlap_tier(profile: _SourceProfile, ranked: list[_ScoredGame]) -> list[Game]:
    """Anything sharing a genre or specialized signal, regardless of score."""
    return [
        game for game, _ in ranked
        if not profile.has_genres or profile.shares_content(game)
    ]


def _closest_tier(_profile: _SourceProfile, ranked: list[_ScoredGame]) -> list[Game]:
    """Last resort: a niche title whose genres nothing else in the catalog shares."""
    return [game for game, _ in ranked]


def _diversify(source: Game, ordered: list[Game], display_limit: int) -> list[Game]:
    source_series = series_key_for_title(source.title)
    series_counts: dict[str, int] = {}
    selected: list[Game] = []
    overflow: list[Game] = []

    for candidate in ordered:
        series = series_key_for_title(candidate.title)
        if (
            source_series
            and series == source_series
            and series_counts.get(series, 0) >= SIMILAR_MAX_SAME_SERIES
        ):
            overflow.append(candidate)
            continue
        selected.append(candidate)
        if series:
            series_counts[series] = series_counts.get(series, 0) + 1
        if len(selected) >= display_limit:
            return selected

    return (selected + overflow)[:display_limit]
