"""
"Games like X" similarity ranking — server-side port of the algorithm that used
to live in the frontend (GameDetailPage.tsx). Moving it here lets a single DB
query supply candidates instead of the frontend firing 5-6 separate /api/games
requests and re-scoring hundreds of games in the browser on every page load.

Public API:
  find_similar_games(db, source, limit) -> list[Game]
  find_series_games(db, source, limit)  -> list[Game]
  series_key_for_title(title)           -> str
"""

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, noload

from ..models import Game

SIMILAR_MIN_SCORE = 42
SIMILAR_FALLBACK_MIN_SCORE = 24
SIMILAR_MIN_RESULTS = 6
SIMILAR_MAX_SAME_SERIES = 3
SIMILAR_CANDIDATE_POOL = 320
SIMILAR_GENRE_POOL = 140
SIMILAR_DEVELOPER_POOL = 40
SIMILAR_SERIES_POOL = 40
SIMILAR_SIGNAL_POOL = 70

PLATFORM_GENRES = {"pc", "steam", "mac", "linux", "playstation", "xbox", "nintendo", "mobile"}
LOW_SIGNAL_GENRES = {"adventure", "action", "indie", "casual", "simulation", "sports"}

GENRE_WEIGHTS: dict[str, float] = {
    "rpg": 16, "strategy": 18, "jrpg": 22, "soulslike": 24, "stealth": 19, "horror": 20,
    "puzzle": 18, "racing": 20, "platformer": 20, "shooter": 18, "fighting": 20,
    "survival": 22, "narrative": 20, "isometric": 28, "tactical": 30, "turn-based": 30,
    "turn based": 30, "crpg": 34, "co-op": 12, "coop": 12,
    "actionAdventure": 16, "cinematic": 22, "thirdPerson": 24, "postApocalyptic": 28,
    "openWorld": 12, "firstPerson": 10, "immersiveSim": 22,
    "dialogueRpg": 34, "detective": 30, "political": 18, "nonCombat": 24,
}

KEYWORD_GROUPS: dict[str, list[str]] = {
    "crpg": ["crpg", "computer role-playing", "tabletop", "dungeons", "d&d", "pathfinder",
             "forgotten realms", "baldur s gate", "baldur's gate", "planescape",
             "pillars of eternity", "divinity original sin", "wasteland"],
    "tactical": ["tactical", "turn-based", "turn based", "positioning", "party-based", "party based"],
    "isometric": ["isometric"],
    "party": ["party", "companions", "companion", "origin story"],
    "narrative": ["narrative", "dialogue", "choices", "choice", "reactive world", "story-rich",
                  "story rich", "story-driven", "story driven", "storytelling"],
    "dialogueRpg": ["dialogue-rich", "dialogue rich", "internal voices", "dice rolls", "skill checks",
                    "role-playing", "role playing", "conversations"],
    "detective": ["detective", "murder", "investigation", "case", "mystery"],
    "political": ["political", "ideology", "ideologies", "revolution", "communist", "fascist"],
    "nonCombat": ["instead of combat", "without combat", "no combat"],
    "cinematic": ["cinematic", "set piece", "set-piece", "character-driven", "character driven",
                  "emotional", "single-player narrative", "single player narrative"],
    "fantasy": ["fantasy", "realm", "demons", "souls", "mythic", "magic", "dragon"],
    "openWorld": ["open world", "sandbox"],
    "postApocalyptic": ["post-apocalyptic", "post apocalyptic", "apocalypse", "pandemic", "infected",
                        "zombie", "zombies", "ravaged world"],
    "thirdPerson": ["third-person", "third person", "over-the-shoulder", "over the shoulder"],
    "firstPerson": ["first-person", "first person", "fps", "vr"],
    "actionAdventure": ["action-adventure", "action adventure"],
    "immersiveSim": ["immersive sim", "systemic", "player choice", "emergent gameplay"],
    "actionCombat": ["soulslike", "hack and slash", "fast-paced", "action combat", "shooter"],
    "shooter": ["shooter", "fps", "first person shooter", "third person shooter", "gunplay"],
    "stealth": ["stealth", "sneak", "assassin"],
    "horror": ["horror", "survival horror", "psychological horror"],
    "survival": ["survival", "crafting", "base building"],
    "puzzle": ["puzzle", "logic", "physics-based", "physics based"],
    "platformer": ["platformer", "metroidvania", "side-scroller", "side scroller"],
    "racing": ["racing", "driving", "motorsport"],
    "management": ["management", "city builder", "colony sim", "automation"],
    "jrpg": ["jrpg", "japanese", "anime"],
    "roguelike": ["roguelike", "rogue-like", "roguelite"],
}

CONFLICTING_GROUPS: list[tuple[str, str]] = [
    ("crpg", "jrpg"), ("crpg", "soulslike"), ("crpg", "roguelike"),
    ("tactical", "soulslike"), ("tactical", "roguelike"), ("narrative", "shooter"),
    ("thirdPerson", "firstPerson"),
]
CRPG_COMPATIBLE_SIGNALS = {"crpg", "tactical", "isometric", "party", "narrative"}
SPECIALIZED_SIGNAL_GROUPS = [
    "crpg", "tactical", "isometric", "jrpg", "soulslike", "roguelike", "shooter",
    "stealth", "horror", "survival", "puzzle", "platformer", "racing", "management",
    "narrative", "cinematic", "thirdPerson", "postApocalyptic", "actionAdventure",
    "openWorld", "immersiveSim", "dialogueRpg", "detective", "political", "nonCombat",
]
KNOWN_SERIES_SIGNALS: dict[str, set[str]] = {
    "last us": {"thirdPerson", "cinematic", "narrative", "stealth", "survival", "horror", "postApocalyptic"},
    "uncharted": {"thirdPerson", "cinematic", "narrative", "actionAdventure"},
    "tomb raider": {"thirdPerson", "cinematic", "survival", "actionAdventure"},
    "resident evil": {"thirdPerson", "horror", "survival", "shooter"},
    "dead space": {"thirdPerson", "horror", "survival", "shooter"},
    "alan wake": {"thirdPerson", "cinematic", "narrative", "horror"},
}
SIGNAL_SEARCH_TERMS: dict[str, list[str]] = {
    "thirdPerson": ["third person", "third-person", "over the shoulder", "over-the-shoulder"],
    "cinematic": ["cinematic", "story-driven", "single-player narrative", "single player narrative"],
    "postApocalyptic": ["post-apocalyptic", "post apocalyptic", "pandemic", "infected", "zombie"],
    "stealth": ["stealth"],
    "survival": ["survival horror", "survival"],
}
SIGNAL_SEARCH_PRIORITY = ["thirdPerson", "cinematic", "postApocalyptic", "stealth", "survival"]

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_SERIES_STOPWORDS_RE = re.compile(
    r"\b(game of the year|goty|definitive|enhanced|complete|ultimate|deluxe|"
    r"director s cut|remastered|remake|edition|collection)\b"
)
_SERIES_NUMERAL_RE = re.compile(r"\b(i|ii|iii|iv|v|vi|vii|viii|ix|x|\d+)\b")
_SERIES_FILLER_WORDS = {"the", "and", "of", "a", "an", "s"}


def _normalize_signal(value: str) -> str:
    return _NON_ALNUM_RE.sub(" ", value.lower()).strip()


@lru_cache(maxsize=4096)
def _phrase_pattern(phrase: str) -> re.Pattern[str] | None:
    normalized = _normalize_signal(phrase)
    if not normalized:
        return None
    return re.compile(rf"(^| ){re.escape(normalized)}( |$)")


def _has_signal_phrase(text: str, phrase: str) -> bool:
    pattern = _phrase_pattern(phrase)
    return bool(pattern and pattern.search(text))


@lru_cache(maxsize=8192)
def _meaningful_genres_from_tuple(genres: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        g for g in (_normalize_signal(genre) for genre in genres)
        if g and g not in PLATFORM_GENRES and g != "uncategorized" and g != "deal"
    )


def _meaningful_genres(game: Game) -> list[str]:
    return list(_meaningful_genres_from_tuple(tuple(game.genres or [])))


@lru_cache(maxsize=4096)
def _title_series_key(title: str) -> str:
    normalized = _normalize_signal(title)
    normalized = _SERIES_STOPWORDS_RE.sub(" ", normalized)
    normalized = _SERIES_NUMERAL_RE.sub(" ", normalized)
    tokens = [t for t in normalized.split(" ") if t and t not in _SERIES_FILLER_WORDS]

    if tokens[:2] == ["elder", "scrolls"]:
        return "elder scrolls"
    if tokens[:2] == ["baldur", "gate"]:
        return "baldur gate"
    if tokens and tokens[0] == "uncharted":
        return "uncharted"
    if tokens[:2] == ["tomb", "raider"]:
        return "tomb raider"
    if tokens[:2] == ["resident", "evil"]:
        return "resident evil"
    if tokens[:2] == ["dead", "space"]:
        return "dead space"
    if tokens[:2] == ["alan", "wake"]:
        return "alan wake"
    if tokens[:2] == ["mass", "effect"]:
        return "mass effect"
    if tokens[:2] == ["deus", "ex"]:
        return "deus ex"
    if tokens[:2] == ["god", "war"]:
        return "god war"
    if tokens[:2] == ["red", "dead"]:
        return "red dead"
    if tokens[:2] == ["final", "fantasy"]:
        return f"final fantasy {tokens[2] if len(tokens) > 2 else ''}".strip()
    return " ".join(tokens[:2])


@lru_cache(maxsize=8192)
def _text_signals_cached(
    game_id: int,
    title: str,
    summary_short: str,
    summary: str,
    genres: tuple[str, ...],
) -> frozenset[str]:
    del game_id
    text = _normalize_signal(" ".join([
        title,
        summary_short,
        summary,
        *genres,
    ]))
    signals = set(_meaningful_genres_from_tuple(genres))
    for group, words in KEYWORD_GROUPS.items():
        if any(_has_signal_phrase(text, word) for word in words):
            signals.add(group)
    signals.update(KNOWN_SERIES_SIGNALS.get(_title_series_key(title), set()))
    return frozenset(signals)


def _text_signals(game: Game) -> set[str]:
    return set(_text_signals_cached(
        game.id,
        game.title,
        game.summary_short or "",
        game.summary or "",
        tuple(game.genres or []),
    ))


@dataclass(frozen=True)
class _SimilarityContext:
    source_genres: frozenset[str]
    candidate_genres: frozenset[str]
    source_signals: frozenset[str]
    candidate_signals: frozenset[str]


def _similarity_context(source: Game, candidate: Game) -> _SimilarityContext:
    return _SimilarityContext(
        source_genres=frozenset(_meaningful_genres(source)),
        candidate_genres=frozenset(_meaningful_genres(candidate)),
        source_signals=frozenset(_text_signals(source)),
        candidate_signals=frozenset(_text_signals(candidate)),
    )


def _genre_similarity_score(source: Game, candidate: Game) -> float:
    context = _similarity_context(source, candidate)
    score, strong_matches = _shared_genre_score(context)
    signal_score, signal_matches = _shared_signal_score(context)
    score += signal_score
    strong_matches += signal_matches
    score += _conflicting_signal_penalty(context)
    if strong_matches == 0 and context.source_genres & context.candidate_genres:
        score -= 18

    shared_specialized = _shared_specialized_signal_count(context)
    if shared_specialized >= 2:
        score += (shared_specialized - 1) * 7

    if {"survival", "horror"} <= context.source_signals and {"survival", "horror"} <= context.candidate_signals:
        score += 10
    if {"cinematic", "narrative"} <= context.source_signals and {"cinematic", "narrative"} <= context.candidate_signals:
        score += 10
    if "postApocalyptic" in context.source_signals and "postApocalyptic" in context.candidate_signals:
        score += 12

    score += _crpg_profile_score(context)
    if _is_deep_rpg_profile(source):
        score += _deep_rpg_profile_score(context)
    score += _profile_mismatch_penalty(context)
    score += _catalog_context_score(source, candidate)
    return score


def _shared_genre_score(context: _SimilarityContext) -> tuple[float, int]:
    score = 0.0
    strong_matches = 0
    for genre in context.candidate_genres & context.source_genres:
        weight = GENRE_WEIGHTS.get(genre, 7 if genre in LOW_SIGNAL_GENRES else 13)
        score += weight
        if weight >= 16:
            strong_matches += 1
    return score, strong_matches


def _shared_signal_score(context: _SimilarityContext) -> tuple[float, int]:
    shared_signals = (
        context.candidate_signals
        & context.source_signals
        - context.candidate_genres
    )
    return sum(GENRE_WEIGHTS.get(signal, 18) for signal in shared_signals), len(shared_signals)


def _conflicting_signal_penalty(context: _SimilarityContext) -> float:
    penalty = 0.0
    for left, right in CONFLICTING_GROUPS:
        if (
            left in context.source_signals
            and right in context.candidate_signals
            and right not in context.source_signals
        ):
            penalty -= 26
        if (
            right in context.source_signals
            and left in context.candidate_signals
            and left not in context.source_signals
        ):
            penalty -= 26
    return penalty


def _shared_specialized_signal_count(context: _SimilarityContext) -> int:
    return sum(
        signal in context.source_signals and signal in context.candidate_signals
        for signal in SPECIALIZED_SIGNAL_GROUPS
    )


def _crpg_profile_score(context: _SimilarityContext) -> float:
    if not ({"crpg", "tactical", "isometric"} & context.source_signals):
        return 0.0
    score = 0.0
    structure = {
        "tactical", "isometric", "turn-based", "turn based", "party",
    } & context.candidate_signals
    if "rpg" not in context.candidate_genres and "rpg" not in context.candidate_signals:
        score -= 48
    if "isometric" in context.candidate_signals:
        score += 24
    if {"tactical", "turn-based", "turn based"} & context.candidate_signals:
        score += 24
    if "party" in context.candidate_signals:
        score += 12
    if {"strategy", "rpg"} <= context.candidate_genres:
        score += 12
    if "action" in context.candidate_genres and not structure:
        score -= 22
    return score


def _deep_rpg_profile_score(context: _SimilarityContext) -> float:
    score = 0.0
    structure = {
        "crpg", "party", "isometric", "tactical", "turn-based", "turn based",
        "dialogueRpg", "detective", "nonCombat",
    } & context.candidate_signals
    candidate_has_rpg = (
        "rpg" in context.candidate_genres
        or "rpg" in context.candidate_signals
    )
    if not candidate_has_rpg:
        score -= 90
    if structure:
        score += len(structure) * 16
    if "strategy" in context.candidate_genres and candidate_has_rpg:
        score += 14
    if "narrative" in context.candidate_signals and candidate_has_rpg:
        score += 10
    if "jrpg" in context.candidate_signals and "jrpg" not in context.source_signals:
        score -= 30
    if "casual" in context.candidate_genres and not structure:
        score -= 45
    if (
        "action" in context.candidate_genres
        and not structure
        and "party" not in context.candidate_signals
    ):
        score -= 35
    if {"platformer", "shooter"} & context.candidate_signals:
        score -= 18
    return score


def _profile_mismatch_penalty(context: _SimilarityContext) -> float:
    penalty = 0.0
    if (
        "thirdPerson" in context.source_signals
        and "firstPerson" in context.candidate_signals
        and "thirdPerson" not in context.candidate_signals
    ):
        penalty -= 24
    if (
        "roguelike" in context.candidate_signals
        and "roguelike" not in context.source_genres
    ):
        penalty -= 14
    if (
        "shooter" in context.candidate_signals
        and {"cinematic", "thirdPerson", "narrative"} & context.source_signals
        and not (
            {
                "horror", "survival", "stealth", "narrative", "cinematic",
                "postApocalyptic",
            }
            & context.candidate_signals
        )
    ):
        penalty -= 16
    return penalty


def _catalog_context_score(source: Game, candidate: Game) -> float:
    shared_platforms = sum(platform in source.platforms for platform in candidate.platforms)
    score = min(shared_platforms, 3) * 2
    if source.developer and candidate.developer and source.developer == candidate.developer:
        score += 30
    source_series = _title_series_key(source.title)
    if source_series and source_series == _title_series_key(candidate.title):
        score += 110
    return score + min(max(candidate.rank_score or candidate.metrix_score or 0, 0), 100) / 25


def _shared_specialized_signals(source: Game, candidate: Game) -> int:
    source_signals = _text_signals(source)
    candidate_signals = _text_signals(candidate)
    return sum(1 for s in SPECIALIZED_SIGNAL_GROUPS if s in source_signals and s in candidate_signals)


def _shared_meaningful_genres(source: Game, candidate: Game) -> int:
    source_genres = set(_meaningful_genres(source))
    return sum(1 for g in _meaningful_genres(candidate) if g in source_genres)


def _has_specialized_signals(game: Game) -> bool:
    signals = _text_signals(game)
    return any(s in signals for s in SPECIALIZED_SIGNAL_GROUPS)


def _is_same_series(source: Game, candidate: Game) -> bool:
    source_series = _title_series_key(source.title)
    candidate_series = _title_series_key(candidate.title)
    return bool(source_series and candidate_series and source_series == candidate_series)


def _is_deep_rpg_profile(game: Game) -> bool:
    genres = set(_meaningful_genres(game))
    signals = _text_signals(game)
    if "rpg" not in genres and "rpg" not in signals:
        return False
    if "action" in genres and not ({"crpg", "party", "isometric", "tactical", "dialogueRpg", "detective"} & signals):
        return False
    return bool({"narrative", "dialogueRpg", "detective", "crpg", "party", "isometric", "tactical"} & signals)


def _passes_similarity_gate(source: Game, candidate: Game) -> bool:
    context = _similarity_context(source, candidate)
    same_series = _is_same_series(source, candidate)
    same_developer = bool(source.developer and candidate.developer and source.developer == candidate.developer)

    if same_series or same_developer:
        return True

    if _is_cinematic_to_systemic_mismatch(context):
        return False

    if _is_deep_rpg_profile(source) and not _passes_deep_rpg_gate(context):
        return False

    if (
        "rpg" in context.source_genres
        and "rpg" not in context.candidate_genres
        and "crpg" not in context.candidate_signals
    ):
        return False

    if not _passes_crpg_gate(context):
        return False
    return _passes_specialized_signal_gate(context)


def _is_cinematic_to_systemic_mismatch(context: _SimilarityContext) -> bool:
    source_is_cinematic_action = bool(
        {
            "cinematic", "thirdPerson", "postApocalyptic", "survival", "horror",
        }
        & context.source_signals
        and (
            "action" in context.source_genres
            or "actionAdventure" in context.source_signals
        )
    )
    candidate_is_systemic_rpg = bool(
        {"crpg", "tactical", "isometric"} & context.candidate_signals
        or (
            "rpg" in context.candidate_genres
            and "action" not in context.candidate_genres
            and "shooter" not in context.candidate_signals
            and "horror" not in context.candidate_signals
            and "survival" not in context.candidate_signals
        )
    )
    return source_is_cinematic_action and candidate_is_systemic_rpg


def _passes_deep_rpg_gate(context: _SimilarityContext) -> bool:
    candidate_has_rpg = (
        "rpg" in context.candidate_genres
        or "rpg" in context.candidate_signals
    )
    deep_overlap = bool(
        {
            "crpg", "party", "isometric", "tactical", "turn-based", "turn based",
            "dialogueRpg", "detective", "nonCombat",
        }
        & context.candidate_signals
        or ("strategy" in context.candidate_genres and candidate_has_rpg)
    )
    if not candidate_has_rpg:
        return False
    if "casual" in context.candidate_genres and not deep_overlap:
        return False
    if (
        "jrpg" in context.candidate_signals
        and "jrpg" not in context.source_signals
        and not deep_overlap
    ):
        return False
    return not (
        "action" in context.candidate_genres
        and not deep_overlap
        and "party" not in context.candidate_signals
    )


def _passes_crpg_gate(context: _SimilarityContext) -> bool:
    source_is_crpg = bool(
        {"crpg", "tactical", "isometric"} & context.source_signals
    )
    if not source_is_crpg:
        return True
    if not (CRPG_COMPATIBLE_SIGNALS & context.candidate_signals):
        return False
    return (
        "rpg" in context.candidate_genres
        and (
            "strategy" in context.candidate_genres
            or "isometric" in context.candidate_genres
            or bool(
                {
                    "crpg", "tactical", "isometric", "turn-based", "turn based",
                    "party",
                }
                & context.candidate_signals
            )
        )
    )


def _passes_specialized_signal_gate(context: _SimilarityContext) -> bool:
    if (
        "jrpg" in context.source_signals
        and "jrpg" not in context.candidate_signals
    ):
        return False
    if (
        "soulslike" in context.source_signals
        and "soulslike" not in context.candidate_signals
        and "actionCombat" not in context.candidate_signals
    ):
        return False
    if (
        "roguelike" in context.source_genres
        and "roguelike" not in context.candidate_signals
    ):
        return False
    source_shooter_is_primary = (
        "shooter" in context.source_signals
        and not (
            {
                "horror", "survival", "narrative", "cinematic", "thirdPerson",
                "stealth",
            }
            & context.source_signals
        )
    )
    if source_shooter_is_primary and "shooter" not in context.candidate_signals:
        return False
    if (
        "horror" in context.source_signals
        and "horror" not in context.candidate_signals
        and "survival" not in context.candidate_signals
        and not (
            {
                "narrative", "cinematic", "stealth", "postApocalyptic",
                "actionAdventure",
            }
            & context.candidate_signals
        )
    ):
        return False
    return not (
        "racing" in context.source_signals
        and "racing" not in context.candidate_signals
    )


def _diversify(source: Game, ranked: list[tuple[Game, float]], display_limit: int) -> list[Game]:
    source_series = _title_series_key(source.title)
    series_counts: dict[str, int] = {}
    selected: list[Game] = []

    for candidate, _score in ranked:
        series = _title_series_key(candidate.title)
        is_same_series = bool(source_series and series and source_series == series)
        if is_same_series and series_counts.get(series, 0) >= SIMILAR_MAX_SAME_SERIES:
            continue
        selected.append(candidate)
        if series:
            series_counts[series] = series_counts.get(series, 0) + 1
        if len(selected) >= display_limit:
            break

    if len(selected) < min(display_limit, len(ranked)):
        selected_slugs = {g.slug for g in selected}
        for candidate, _score in ranked:
            if candidate.slug in selected_slugs:
                continue
            selected.append(candidate)
            selected_slugs.add(candidate.slug)
            if len(selected) >= display_limit:
                break

    return selected[:display_limit]


def rank_similar_games(source: Game, candidates: list[Game], display_limit: int = 10) -> list[Game]:
    by_slug: dict[str, Game] = {}
    for candidate in candidates:
        if candidate.slug == source.slug or candidate.content_type != "game":
            continue
        by_slug[candidate.slug] = candidate

    all_ranked = sorted(
        ((c, _genre_similarity_score(source, c)) for c in by_slug.values()),
        key=lambda item: (item[1], item[0].rank_score),
        reverse=True,
    )

    source_is_specialized = _has_specialized_signals(source)
    source_has_genres = len(_meaningful_genres(source)) > 0
    primary_min_score = SIMILAR_MIN_SCORE if source_is_specialized else SIMILAR_FALLBACK_MIN_SCORE

    def primary_ok(candidate: Game, score: float) -> bool:
        if not _passes_similarity_gate(source, candidate) or score < primary_min_score:
            return False
        if not source_has_genres:
            return True
        return (
            _shared_meaningful_genres(source, candidate) > 0
            or _shared_specialized_signals(source, candidate) > 0
            or _is_same_series(source, candidate)
            or bool(source.developer and candidate.developer and source.developer == candidate.developer)
        )

    primary = [(c, s) for c, s in all_ranked if primary_ok(c, s)]
    primary_slugs = {c.slug for c, _ in primary}

    def fallback_ok(candidate: Game, score: float) -> bool:
        if candidate.slug in primary_slugs or score < SIMILAR_FALLBACK_MIN_SCORE:
            return False
        if not source_has_genres:
            return True
        return (
            _shared_specialized_signals(source, candidate) > 0
            or _shared_meaningful_genres(source, candidate) > 0
            or _is_same_series(source, candidate)
        )

    fallback = [(c, s) for c, s in all_ranked if fallback_ok(c, s)]

    diversified = _diversify(source, primary + fallback, display_limit)
    if len(diversified) >= SIMILAR_MIN_RESULTS:
        return diversified

    selected_slugs = {c.slug for c in diversified}
    broad_backfill = [
        (c, s) for c, s in all_ranked
        if c.slug not in selected_slugs
        and (not source_has_genres or _shared_meaningful_genres(source, c) > 0 or _shared_specialized_signals(source, c) > 0)
    ]

    with_backfill = _diversify(
        source,
        [(c, _genre_similarity_score(source, c)) for c in diversified] + broad_backfill,
        display_limit,
    )
    if len(with_backfill) >= SIMILAR_MIN_RESULTS or len(with_backfill) >= len(all_ranked):
        return with_backfill

    # Last resort: no genre/signal overlap survived any gate above (e.g. a niche
    # title with genres nothing else in the catalog shares). Rather than showing
    # nothing, fall back to the closest-ranked catalog entries regardless of genre.
    final_slugs = {c.slug for c in with_backfill}
    closest_by_rank = [(c, s) for c, s in all_ranked if c.slug not in final_slugs]

    return _diversify(
        source,
        [(c, _genre_similarity_score(source, c)) for c in with_backfill] + closest_by_rank,
        display_limit,
    )


def _search_genres(source: Game) -> list[str]:
    """Mirrors the frontend's similarSearchGenres: top 4 genres by weight, platform tags excluded."""
    seen: set[str] = set()
    ordered: list[str] = []
    for genre in source.genres:
        normalized = _normalize_signal(genre)
        if not normalized or normalized in PLATFORM_GENRES or normalized == "uncategorized" or genre == "Deal":
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(genre)
    ordered.sort(key=lambda g: GENRE_WEIGHTS.get(_normalize_signal(g), 10), reverse=True)
    return ordered[:4]


def _series_title_pattern(source: Game) -> str | None:
    series = _title_series_key(source.title)
    if not series or len(series) < 5:
        return None
    return f"%{'%'.join(series.split())}%"


def _search_signal_terms(source: Game) -> list[tuple[str, list[str]]]:
    source_signals = _text_signals(source)
    source_genres = set(_meaningful_genres(source))
    if not (
        {"thirdPerson", "cinematic", "postApocalyptic", "survival", "horror", "stealth"} & source_signals
        and ("action" in source_genres or "shooter" in source_signals or "horror" in source_signals or "survival" in source_signals)
    ):
        return []
    return [
        (signal, SIGNAL_SEARCH_TERMS[signal])
        for signal in SIGNAL_SEARCH_PRIORITY
        if signal in source_signals
    ][:3]


# ── Franchise / series lookup ─────────────────────────────────────────────────

# A series key's first token must be at least this long to identify a franchise
# on its own ("persona", "witcher", "bioshock"). Shorter first tokens ("god",
# "dark", "mass") are too generic, so those fall back to full-key equality —
# which still works because numerals/editions are already stripped from keys
# ("Dark Souls III" and "Dark Souls II" both normalize to "dark souls").
_FRANCHISE_MIN_FIRST_TOKEN = 6
_SERIES_CANDIDATE_POOL = 80


def series_key_for_title(title: str) -> str:
    return _title_series_key(title)


def _same_franchise(source_key: str, candidate_key: str) -> bool:
    if not source_key or not candidate_key:
        return False
    if source_key == candidate_key:
        return True
    source_first = source_key.split()[0]
    candidate_first = candidate_key.split()[0]
    return source_first == candidate_first and len(source_first) >= _FRANCHISE_MIN_FIRST_TOKEN


def find_series_games(db: Session, source: Game, limit: int = 8) -> list[Game]:
    """
    Other entries in the source game's franchise, oldest first.

    Authoritative membership comes from IGDB's franchise/collection (`Game.franchise`)
    when present; the title-key heuristic then fills in siblings IGDB has not tagged
    yet, so "Persona 5 Royal" matches "Persona 4 Golden" but not "Personal Trainer".
    """
    matches: dict[int, Game] = {}

    if source.franchise:
        for game in db.scalars(
            select(Game)
            .options(noload(Game.price_snapshots))
            .where(Game.content_type == "game")
            .where(Game.id != source.id)
            .where(Game.franchise == source.franchise)
            .order_by(Game.rank_score.desc())
            .limit(_SERIES_CANDIDATE_POOL)
        ):
            matches[game.id] = game

    source_key = _title_series_key(source.title)
    if source_key:
        first_token = source_key.split()[0]
        pattern = (
            f"%{first_token}%"
            if len(first_token) >= _FRANCHISE_MIN_FIRST_TOKEN
            else _series_title_pattern(source)
        )
        if pattern:
            for game in db.scalars(
                select(Game)
                .options(noload(Game.price_snapshots))
                .where(Game.content_type == "game")
                .where(Game.id != source.id)
                .where(Game.title.ilike(pattern))
                .order_by(Game.rank_score.desc())
                .limit(_SERIES_CANDIDATE_POOL)
            ):
                if game.id not in matches and _same_franchise(source_key, _title_series_key(game.title)):
                    matches[game.id] = game

    ordered = sorted(matches.values(), key=lambda g: (g.release_year or 0, g.release_date or date.min))
    return ordered[:limit]


def _genre_match_sql() -> str:
    """EXISTS clause matching a value inside the games.genres JSON array."""
    return (
        "EXISTS (SELECT 1 FROM jsonb_array_elements_text(games.genres::jsonb)"
        " AS value WHERE value = :genre)"
    )


def find_similar_games(db: Session, source: Game, display_limit: int = 10) -> list[Game]:
    """
    Pull candidates in a small, fixed number of DB queries and rank them in-process.
    Combines a top-ranked global pool with genre-targeted and same-developer pools so
    niche/low-rank titles still see genre-accurate matches, not just "best overall".
    """
    by_slug: dict[str, Game] = {}
    genre_match_sql = _genre_match_sql()

    def _collect(stmt):
        for game in db.scalars(stmt):
            if game.id != source.id:
                by_slug[game.slug] = game

    _collect(
        select(Game)
        .options(noload(Game.price_snapshots))
        .where(Game.content_type == "game")
        .order_by(Game.rank_score.desc())
        .limit(SIMILAR_CANDIDATE_POOL)
    )

    for genre in _search_genres(source):
        _collect(
            select(Game)
            .options(noload(Game.price_snapshots))
            .where(Game.content_type == "game")
            .where(text(genre_match_sql))
            .params(genre=genre)
            .order_by(Game.rank_score.desc())
            .limit(SIMILAR_GENRE_POOL)
        )

    series_pattern = _series_title_pattern(source)
    if series_pattern:
        _collect(
            select(Game)
            .options(noload(Game.price_snapshots))
            .where(Game.content_type == "game")
            .where(Game.title.ilike(series_pattern))
            .order_by(Game.rank_score.desc())
            .limit(SIMILAR_SERIES_POOL)
        )

    for _signal, terms in _search_signal_terms(source):
        clauses = []
        for term in terms:
            pattern = f"%{term}%"
            clauses.extend([
                Game.title.ilike(pattern),
                Game.summary.ilike(pattern),
                Game.summary_short.ilike(pattern),
            ])
        _collect(
            select(Game)
            .options(noload(Game.price_snapshots))
            .where(Game.content_type == "game")
            .where(or_(*clauses))
            .order_by(Game.rank_score.desc())
            .limit(SIMILAR_SIGNAL_POOL)
        )

    if source.developer:
        _collect(
            select(Game)
            .options(noload(Game.price_snapshots))
            .where(Game.content_type == "game")
            .where(Game.developer == source.developer)
            .order_by(Game.rank_score.desc())
            .limit(SIMILAR_DEVELOPER_POOL)
        )

    return rank_similar_games(source, list(by_slug.values()), display_limit)
