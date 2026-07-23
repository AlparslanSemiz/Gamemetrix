"""Hard yes/no filters applied before a candidate may be ranked.

Scoring says how close two games are; gates say whether the pairing is
admissible at all. Same-series and same-developer pairings bypass every gate.
"""

from ...models import Game
from .profiles import (
    SimilarityContext,
    build_context,
    is_deep_rpg_profile,
    is_same_developer,
    is_same_series,
)
from .taxonomy import (
    CRPG_COMPATIBLE_SIGNALS,
    CRPG_STRUCTURE_SIGNALS,
    CRPG_TRIGGER_SIGNALS,
    CINEMATIC_ACTION_SIGNALS,
    DEEP_RPG_STRUCTURE_SIGNALS,
    HORROR_ADJACENT_SIGNALS,
    SHOOTER_SOFTENING_SIGNALS,
)


def passes_similarity_gate(source: Game, candidate: Game) -> bool:
    if is_same_series(source, candidate) or is_same_developer(source, candidate):
        return True

    context = build_context(source, candidate)
    if _is_cinematic_to_systemic_mismatch(context):
        return False
    if is_deep_rpg_profile(source) and not _passes_deep_rpg_gate(context):
        return False
    if not _passes_rpg_genre_gate(context):
        return False
    if not _passes_crpg_gate(context):
        return False
    return _passes_specialized_signal_gate(context)


def _is_cinematic_to_systemic_mismatch(context: SimilarityContext) -> bool:
    source_is_cinematic_action = bool(
        CINEMATIC_ACTION_SIGNALS & context.source_signals
        and (
            "action" in context.source_genres
            or "actionAdventure" in context.source_signals
        )
    )
    candidate_is_systemic_rpg = bool(
        CRPG_TRIGGER_SIGNALS & context.candidate_signals
        or (
            "rpg" in context.candidate_genres
            and "action" not in context.candidate_genres
            and not {"shooter", "horror", "survival"} & context.candidate_signals
        )
    )
    return source_is_cinematic_action and candidate_is_systemic_rpg


def _passes_deep_rpg_gate(context: SimilarityContext) -> bool:
    if not context.candidate_is_rpg:
        return False

    deep_overlap = bool(
        DEEP_RPG_STRUCTURE_SIGNALS & context.candidate_signals
        or "strategy" in context.candidate_genres
    )
    if deep_overlap:
        return True
    if "casual" in context.candidate_genres:
        return False
    if "jrpg" in context.candidate_signals and "jrpg" not in context.source_signals:
        return False
    return not (
        "action" in context.candidate_genres
        and "party" not in context.candidate_signals
    )


def _passes_rpg_genre_gate(context: SimilarityContext) -> bool:
    if "rpg" not in context.source_genres:
        return True
    return "rpg" in context.candidate_genres or "crpg" in context.candidate_signals


def _passes_crpg_gate(context: SimilarityContext) -> bool:
    if not context.source_is_crpg:
        return True
    if not CRPG_COMPATIBLE_SIGNALS & context.candidate_signals:
        return False
    if "rpg" not in context.candidate_genres:
        return False
    return bool(
        {"strategy", "isometric"} & context.candidate_genres
        or CRPG_STRUCTURE_SIGNALS & context.candidate_signals
        or "crpg" in context.candidate_signals
    )


def _passes_specialized_signal_gate(context: SimilarityContext) -> bool:
    return all(
        check(context)
        for check in (
            _jrpg_requires_jrpg,
            _soulslike_requires_action_combat,
            _roguelike_requires_roguelike,
            _pure_shooter_requires_shooter,
            _horror_requires_adjacent_mood,
            _racing_requires_racing,
        )
    )


def _jrpg_requires_jrpg(context: SimilarityContext) -> bool:
    return "jrpg" not in context.source_signals or "jrpg" in context.candidate_signals


def _soulslike_requires_action_combat(context: SimilarityContext) -> bool:
    if "soulslike" not in context.source_signals:
        return True
    return bool({"soulslike", "actionCombat"} & context.candidate_signals)


def _roguelike_requires_roguelike(context: SimilarityContext) -> bool:
    return "roguelike" not in context.source_genres or "roguelike" in context.candidate_signals


def _pure_shooter_requires_shooter(context: SimilarityContext) -> bool:
    source_shooter_is_primary = (
        "shooter" in context.source_signals
        and not SHOOTER_SOFTENING_SIGNALS & context.source_signals
    )
    return not source_shooter_is_primary or "shooter" in context.candidate_signals


def _horror_requires_adjacent_mood(context: SimilarityContext) -> bool:
    if "horror" not in context.source_signals:
        return True
    return bool(
        {"horror", "survival"} & context.candidate_signals
        or HORROR_ADJACENT_SIGNALS & context.candidate_signals
    )


def _racing_requires_racing(context: SimilarityContext) -> bool:
    return "racing" not in context.source_signals or "racing" in context.candidate_signals
