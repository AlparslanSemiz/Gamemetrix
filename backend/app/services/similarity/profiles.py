"""Comparisons between two games, and the profile predicates the gates rely on."""

from dataclasses import dataclass

from ...models import Game
from .signals import meaningful_genres, series_key_for_title, text_signals
from .taxonomy import (
    CRPG_TRIGGER_SIGNALS,
    DEEP_RPG_CORE_SIGNALS,
    DEEP_RPG_DEPTH_SIGNALS,
    SPECIALIZED_SIGNAL_GROUPS,
)


@dataclass(frozen=True)
class SimilarityContext:
    source_genres: frozenset[str]
    candidate_genres: frozenset[str]
    source_signals: frozenset[str]
    candidate_signals: frozenset[str]

    @property
    def shared_genres(self) -> frozenset[str]:
        return self.source_genres & self.candidate_genres

    @property
    def shared_signals(self) -> frozenset[str]:
        return self.source_signals & self.candidate_signals

    @property
    def candidate_is_rpg(self) -> bool:
        return "rpg" in self.candidate_genres or "rpg" in self.candidate_signals

    @property
    def source_is_crpg(self) -> bool:
        return bool(CRPG_TRIGGER_SIGNALS & self.source_signals)

    def shared_specialized_count(self) -> int:
        return sum(signal in self.shared_signals for signal in SPECIALIZED_SIGNAL_GROUPS)


def build_context(source: Game, candidate: Game) -> SimilarityContext:
    return SimilarityContext(
        source_genres=frozenset(meaningful_genres(source)),
        candidate_genres=frozenset(meaningful_genres(candidate)),
        source_signals=text_signals(source),
        candidate_signals=text_signals(candidate),
    )


def has_specialized_signals(game: Game) -> bool:
    signals = text_signals(game)
    return any(signal in signals for signal in SPECIALIZED_SIGNAL_GROUPS)


def is_deep_rpg_profile(game: Game) -> bool:
    genres = set(meaningful_genres(game))
    signals = text_signals(game)
    if "rpg" not in genres and "rpg" not in signals:
        return False
    if "action" in genres and not DEEP_RPG_CORE_SIGNALS & signals:
        return False
    return bool(DEEP_RPG_DEPTH_SIGNALS & signals)


def is_same_series(source: Game, candidate: Game) -> bool:
    source_key = series_key_for_title(source.title)
    return bool(source_key and source_key == series_key_for_title(candidate.title))


def is_same_developer(source: Game, candidate: Game) -> bool:
    return bool(source.developer and source.developer == candidate.developer)


def shared_meaningful_genre_count(source: Game, candidate: Game) -> int:
    source_genres = set(meaningful_genres(source))
    return sum(genre in source_genres for genre in meaningful_genres(candidate))


def shared_specialized_signal_count(source: Game, candidate: Game) -> int:
    return build_context(source, candidate).shared_specialized_count()
