"""
Game list filtering, sorting, and deduplication.

All filter functions accept list[Game] and return a filtered list[Game].
Each function does exactly one thing.

Public API:
  normalized_title(value)         -> str
  canonical_title(value)          -> str
  dedupe_near_duplicates(games)   -> list[Game]
  filter_by_genre                 -> list[Game]
  filter_by_developer             -> list[Game]
  filter_by_publisher             -> list[Game]
  filter_by_platform              -> list[Game]
  filter_by_min_ratings           -> list[Game]
  filter_by_max_ratings           -> list[Game]
  filter_has_award                -> list[Game]
  filter_has_critic               -> list[Game]
  filter_min_live_sources         -> list[Game]
  sort_in_memory(games, sort, dir)-> list[Game]
"""

import re

from ..models import Game
from ..integrations.source_registry import CRITIC_SOURCES


# Year tolerance for deduplication: editions of the same game within this
# many years are treated as the same title and the better-scored entry wins.
_SAME_TITLE_YEAR_TOLERANCE = 4    # exact title match (e.g. same game, two imports)
_EDITION_YEAR_TOLERANCE = 10      # canonical title match (e.g. Remastered 10 years later)

_EDITION_SUFFIX_RE = re.compile(
    r"[\s:–—\-]+(?:"
    r"definitive edition|royal|remastered?|remake(?:d)?|enhanced edition|"
    r"complete edition|goty|game of the year(?:\s+edition)?|"
    r"anniversary edition|gold edition|platinum edition|legendary edition|"
    r"ultimate edition|deluxe edition|director'?s cut|expanded edition|"
    r"redux|hd(?: remaster)?|4k|the complete edition|origins?"
    r")$",
    re.IGNORECASE,
)


def normalized_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def canonical_title(value: str) -> str:
    stripped = _EDITION_SUFFIX_RE.sub("", value).strip()
    return re.sub(r"[^a-z0-9]+", "", stripped.lower())


def _total_review_count(game: Game) -> int:
    return sum(int(s.get("review_count", 0)) for s in game.source_scores)


def _live_review_count(game: Game) -> int:
    return sum(
        int(s.get("review_count", 0))
        for s in game.source_scores
        if s.get("status") == "live"
    )


def _source_score(game: Game, source_name: str) -> float:
    for s in game.source_scores:
        if str(s.get("source", "")).lower() == source_name.lower():
            return float(s.get("score", 0))
    return 0.0


def _duplicate_quality_key(game: Game) -> tuple[int, int, float, int]:
    return (
        game.live_primary_source_count,
        _total_review_count(game),
        game.metrix_score,
        1 if game.release_year != 1970 else 0,
    )


def dedupe_near_duplicates(games: list[Game]) -> list[Game]:
    deduped: list[Game] = []
    idx_by_key: dict[str, list[int]] = {}

    def _register(game: Game, idx: int) -> None:
        for key in {normalized_title(game.title), canonical_title(game.title)}:
            idx_by_key.setdefault(key, [])
            if idx not in idx_by_key[key]:
                idx_by_key[key].append(idx)

    def _find_match(game: Game) -> int | None:
        norm = normalized_title(game.title)
        canon = canonical_title(game.title)
        for idx in idx_by_key.get(norm, []):
            if abs(deduped[idx].release_year - game.release_year) <= _SAME_TITLE_YEAR_TOLERANCE:
                return idx
        if canon != norm:
            for idx in idx_by_key.get(canon, []):
                if abs(deduped[idx].release_year - game.release_year) <= _EDITION_YEAR_TOLERANCE:
                    return idx
        return None

    for game in games:
        existing_idx = _find_match(game)
        if existing_idx is None:
            new_idx = len(deduped)
            deduped.append(game)
            _register(game, new_idx)
        elif _duplicate_quality_key(game) > _duplicate_quality_key(deduped[existing_idx]):
            deduped[existing_idx] = game
            _register(game, existing_idx)

    return deduped


def filter_by_genre(games: list[Game], genre: str) -> list[Game]:
    return [g for g in games if genre in g.genres]


def filter_by_developer(games: list[Game], developer: str) -> list[Game]:
    return [g for g in games if g.developer and g.developer.lower() == developer.lower()]


def filter_by_publisher(games: list[Game], publisher: str) -> list[Game]:
    return [g for g in games if g.publisher and g.publisher.lower() == publisher.lower()]


def filter_by_platform(games: list[Game], platform: str) -> list[Game]:
    terms = [platform.lower()]
    if platform.lower() == "steam":
        terms.append("pc")
    return [
        g for g in games
        if any(term in stored.lower() for stored in g.platforms for term in terms)
    ]


def filter_by_min_ratings(games: list[Game], min_ratings: int) -> list[Game]:
    return [g for g in games if _live_review_count(g) >= min_ratings]


def filter_by_max_ratings(games: list[Game], max_ratings: int) -> list[Game]:
    return [g for g in games if _live_review_count(g) <= max_ratings]


def filter_has_award(games: list[Game]) -> list[Game]:
    return [g for g in games if g.goty_year is not None or (g.award_count or 0) > 0]


def filter_has_critic(games: list[Game]) -> list[Game]:
    return [
        g for g in games
        if any(
            str(s.get("source")) in CRITIC_SOURCES
            and s.get("status") == "live"
            and float(s.get("score", 0)) > 0
            for s in g.source_scores
        )
    ]


def filter_min_live_sources(games: list[Game], min_live: int) -> list[Game]:
    return [g for g in games if g.live_primary_source_count >= min_live]


def sort_in_memory(games: list[Game], sort: str, direction: str) -> list[Game]:
    reverse = direction == "desc"
    if sort == "review_count":
        return sorted(games, key=_total_review_count, reverse=reverse)
    source_map = {
        "metacritic_score": "Metacritic",
        "opencritic_score": "OpenCritic",
        "steam_score": "Steam",
    }
    if sort in source_map:
        src = source_map[sort]
        return sorted(games, key=lambda g: _source_score(g, src), reverse=reverse)
    if sort == "title" and direction == "desc":
        return sorted(games, key=lambda g: g.title.lower(), reverse=True)
    if sort == "rank_score":
        return sorted(games, key=lambda g: g.rank_score, reverse=reverse)
    return games
