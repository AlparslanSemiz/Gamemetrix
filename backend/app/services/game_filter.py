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

from ..models import Game
from ..integrations.source_registry import CRITIC_SOURCES
from .deduplication import (
    canonical_title,
    dedupe_games_in_memory,
    normalized_title,
    total_review_count,
)


def _total_review_count(game: Game) -> int:
    return total_review_count(game)


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


def dedupe_near_duplicates(games: list[Game]) -> list[Game]:
    return dedupe_games_in_memory(games)


def filter_by_genre(games: list[Game], genre: str) -> list[Game]:
    wanted = genre.strip().lower()
    return [
        g for g in games
        if any(stored.strip().lower() == wanted for stored in g.genres)
    ]


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
