"""How close two games are, as a number. Higher is more similar.

`similarity_score` is the only entry point; every helper contributes one
independent term and knows nothing about the others.
"""

from ...models import Game
from .profiles import SimilarityContext, build_context, is_deep_rpg_profile
from .signals import series_key_for_title
from .taxonomy import (
    CINEMATIC_FOCUS_SIGNALS,
    CONFLICTING_GROUPS,
    CRPG_STRUCTURE_SIGNALS,
    DEEP_RPG_STRUCTURE_SIGNALS,
    DEFAULT_GENRE_WEIGHT,
    DEFAULT_SIGNAL_WEIGHT,
    GENRE_WEIGHTS,
    LOW_SIGNAL_GENRE_WEIGHT,
    LOW_SIGNAL_GENRES,
    SHOOTER_TOLERANT_SIGNALS,
    STRONG_MATCH_WEIGHT,
)

WEAK_GENRE_ONLY_PENALTY = -18
CONFLICTING_SIGNAL_PENALTY = -26
EXTRA_SPECIALIZED_SIGNAL_BONUS = 7
MIN_SPECIALIZED_FOR_BONUS = 2

THEME_PAIR_BONUSES: list[tuple[frozenset[str], float]] = [
    (frozenset({"survival", "horror"}), 10),
    (frozenset({"cinematic", "narrative"}), 10),
    (frozenset({"postApocalyptic"}), 12),
]

CRPG_NO_RPG_PENALTY = -48
CRPG_ISOMETRIC_BONUS = 24
CRPG_TACTICAL_BONUS = 24
CRPG_PARTY_BONUS = 12
CRPG_STRATEGY_RPG_BONUS = 12
CRPG_UNSTRUCTURED_ACTION_PENALTY = -22

DEEP_RPG_NO_RPG_PENALTY = -90
DEEP_RPG_STRUCTURE_BONUS = 16
DEEP_RPG_STRATEGY_BONUS = 14
DEEP_RPG_NARRATIVE_BONUS = 10
DEEP_RPG_FOREIGN_JRPG_PENALTY = -30
DEEP_RPG_CASUAL_PENALTY = -45
DEEP_RPG_UNSTRUCTURED_ACTION_PENALTY = -35
DEEP_RPG_ARCADE_PENALTY = -18

PERSPECTIVE_MISMATCH_PENALTY = -24
UNWANTED_ROGUELIKE_PENALTY = -14
UNWANTED_SHOOTER_PENALTY = -16

PLATFORM_OVERLAP_BONUS = 2
MAX_COUNTED_SHARED_PLATFORMS = 3
SAME_DEVELOPER_BONUS = 30
SAME_SERIES_BONUS = 110
MAX_COUNTED_RANK_SCORE = 100
RANK_SCORE_DIVISOR = 25


def similarity_score(source: Game, candidate: Game) -> float:
    context = build_context(source, candidate)
    genre_score, genre_matches = _shared_genre_score(context)
    signal_score, signal_matches = _shared_signal_score(context)

    score = genre_score + signal_score
    if genre_matches + signal_matches == 0 and context.shared_genres:
        score += WEAK_GENRE_ONLY_PENALTY

    score += _conflicting_signal_penalty(context)
    score += _specialized_overlap_bonus(context)
    score += _theme_pair_bonus(context)
    score += _crpg_profile_score(context)
    if is_deep_rpg_profile(source):
        score += _deep_rpg_profile_score(context)
    score += _profile_mismatch_penalty(context)
    return score + _catalog_context_score(source, candidate)


def _shared_genre_score(context: SimilarityContext) -> tuple[float, int]:
    score = 0.0
    strong_matches = 0
    for genre in context.shared_genres:
        weight = GENRE_WEIGHTS.get(
            genre,
            LOW_SIGNAL_GENRE_WEIGHT if genre in LOW_SIGNAL_GENRES else DEFAULT_GENRE_WEIGHT,
        )
        score += weight
        if weight >= STRONG_MATCH_WEIGHT:
            strong_matches += 1
    return score, strong_matches


def _shared_signal_score(context: SimilarityContext) -> tuple[float, int]:
    shared = context.shared_signals - context.candidate_genres
    return sum(GENRE_WEIGHTS.get(signal, DEFAULT_SIGNAL_WEIGHT) for signal in shared), len(shared)


def _conflicting_signal_penalty(context: SimilarityContext) -> float:
    penalty = 0.0
    for left, right in CONFLICTING_GROUPS:
        for wanted, unwanted in ((left, right), (right, left)):
            if (
                wanted in context.source_signals
                and unwanted in context.candidate_signals
                and unwanted not in context.source_signals
            ):
                penalty += CONFLICTING_SIGNAL_PENALTY
    return penalty


def _specialized_overlap_bonus(context: SimilarityContext) -> float:
    shared = context.shared_specialized_count()
    if shared < MIN_SPECIALIZED_FOR_BONUS:
        return 0.0
    return (shared - 1) * EXTRA_SPECIALIZED_SIGNAL_BONUS


def _theme_pair_bonus(context: SimilarityContext) -> float:
    return sum(
        bonus
        for theme, bonus in THEME_PAIR_BONUSES
        if theme <= context.source_signals and theme <= context.candidate_signals
    )


def _crpg_profile_score(context: SimilarityContext) -> float:
    if not context.source_is_crpg:
        return 0.0

    score = 0.0
    structure = CRPG_STRUCTURE_SIGNALS & context.candidate_signals
    if not context.candidate_is_rpg:
        score += CRPG_NO_RPG_PENALTY
    if "isometric" in context.candidate_signals:
        score += CRPG_ISOMETRIC_BONUS
    if {"tactical", "turn-based", "turn based"} & context.candidate_signals:
        score += CRPG_TACTICAL_BONUS
    if "party" in context.candidate_signals:
        score += CRPG_PARTY_BONUS
    if {"strategy", "rpg"} <= context.candidate_genres:
        score += CRPG_STRATEGY_RPG_BONUS
    if "action" in context.candidate_genres and not structure:
        score += CRPG_UNSTRUCTURED_ACTION_PENALTY
    return score


def _deep_rpg_profile_score(context: SimilarityContext) -> float:
    score = 0.0
    structure = DEEP_RPG_STRUCTURE_SIGNALS & context.candidate_signals
    is_rpg = context.candidate_is_rpg

    if not is_rpg:
        score += DEEP_RPG_NO_RPG_PENALTY
    score += len(structure) * DEEP_RPG_STRUCTURE_BONUS
    if is_rpg and "strategy" in context.candidate_genres:
        score += DEEP_RPG_STRATEGY_BONUS
    if is_rpg and "narrative" in context.candidate_signals:
        score += DEEP_RPG_NARRATIVE_BONUS
    if "jrpg" in context.candidate_signals and "jrpg" not in context.source_signals:
        score += DEEP_RPG_FOREIGN_JRPG_PENALTY
    if "casual" in context.candidate_genres and not structure:
        score += DEEP_RPG_CASUAL_PENALTY
    if (
        "action" in context.candidate_genres
        and not structure
        and "party" not in context.candidate_signals
    ):
        score += DEEP_RPG_UNSTRUCTURED_ACTION_PENALTY
    if {"platformer", "shooter"} & context.candidate_signals:
        score += DEEP_RPG_ARCADE_PENALTY
    return score


def _profile_mismatch_penalty(context: SimilarityContext) -> float:
    penalty = 0.0
    if (
        "thirdPerson" in context.source_signals
        and "firstPerson" in context.candidate_signals
        and "thirdPerson" not in context.candidate_signals
    ):
        penalty += PERSPECTIVE_MISMATCH_PENALTY
    if "roguelike" in context.candidate_signals and "roguelike" not in context.source_genres:
        penalty += UNWANTED_ROGUELIKE_PENALTY
    if (
        "shooter" in context.candidate_signals
        and CINEMATIC_FOCUS_SIGNALS & context.source_signals
        and not SHOOTER_TOLERANT_SIGNALS & context.candidate_signals
    ):
        penalty += UNWANTED_SHOOTER_PENALTY
    return penalty


def _catalog_context_score(source: Game, candidate: Game) -> float:
    shared_platforms = sum(platform in source.platforms for platform in candidate.platforms)
    score = min(shared_platforms, MAX_COUNTED_SHARED_PLATFORMS) * PLATFORM_OVERLAP_BONUS

    if source.developer and source.developer == candidate.developer:
        score += SAME_DEVELOPER_BONUS

    source_series = series_key_for_title(source.title)
    if source_series and source_series == series_key_for_title(candidate.title):
        score += SAME_SERIES_BONUS

    rank = min(max(candidate.rank_score or candidate.metrix_score or 0, 0), MAX_COUNTED_RANK_SCORE)
    return score + rank / RANK_SCORE_DIVISOR
