"""
Game list filtering, sorting, and deduplication.

All filter functions accept list[Game] and return a filtered list[Game].
Each function does exactly one thing.

Public API:
  normalized_title(value)         -> str
  canonical_title(value)          -> str
  escape_like(value)              -> str
  dedupe_near_duplicates(games)   -> list[Game]
  filter_by_genre                 -> list[Game]
  filter_by_developer             -> list[Game]
  filter_by_publisher             -> list[Game]
  filter_by_platform              -> list[Game]
  filter_by_player_mode           -> list[Game]
  filter_by_playtime              -> list[Game]
  filter_by_min_ratings           -> list[Game]
  filter_by_max_ratings           -> list[Game]
  filter_has_award                -> list[Game]
  filter_has_critic               -> list[Game]
  filter_min_live_sources         -> list[Game]
  sort_in_memory(games, sort, dir)-> list[Game]
"""

from ..models import Game, _safe_review_count, _valid_score
from ..integrations.source_registry import CRITIC_SOURCES
from .deduplication import (
    canonical_title,
    dedupe_games_in_memory,
    normalized_title,
    total_review_count,
)


LIKE_ESCAPE_CHAR = "\\"
_MINUTES_PER_HOUR = 60

# Catalogs that predate the game_modes column still carry the signal in their
# genre tags, so a mode filter also accepts these equivalents.
_PLAYER_MODE_GENRE_ALIASES: dict[str, frozenset[str]] = {
    "multiplayer": frozenset({"massively multiplayer", "mmo", "mmorpg", "mmoarpg", "multiplayer", "pvp", "online co-op"}),
    "coop": frozenset({"co-op", "coop", "online co-op", "local co-op"}),
    "singleplayer": frozenset({"single player", "singleplayer"}),
}


def escape_like(value: str) -> str:
    """Escape LIKE wildcards so user input matches literally (use with ilike(..., escape=LIKE_ESCAPE_CHAR))."""
    return (
        value.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
        .replace("%", f"{LIKE_ESCAPE_CHAR}%")
        .replace("_", f"{LIKE_ESCAPE_CHAR}_")
    )


def _total_review_count(game: Game) -> int:
    return total_review_count(game)


def _live_review_count(game: Game) -> int:
    return sum(
        _safe_review_count(s)
        for s in (game.source_scores or [])
        if isinstance(s, dict) and _valid_score(s)
    )


def _source_score(game: Game, source_name: str) -> float:
    for s in (game.source_scores or []):
        if isinstance(s, dict) and _valid_score(s) and str(s.get("source", "")).lower() == source_name.lower():
            return float(s.get("score", 0))
    return 0.0


def dedupe_near_duplicates(games: list[Game]) -> list[Game]:
    return dedupe_games_in_memory(games)


def filter_by_genre(games: list[Game], genre: str) -> list[Game]:
    wanted = genre.strip().lower()
    return [
        g for g in games
        if any(stored.strip().lower() == wanted for stored in g.genres if isinstance(stored, str))
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
        if any(term in stored.lower() for stored in g.platforms if isinstance(stored, str) for term in terms)
    ]


def filter_by_player_mode(games: list[Game], player_mode: str) -> list[Game]:
    wanted = player_mode.strip().lower()
    genre_aliases = _PLAYER_MODE_GENRE_ALIASES.get(wanted, frozenset())
    return [
        g for g in games
        if wanted in {str(mode).strip().lower() for mode in (g.game_modes or [])}
        or any(str(stored).strip().lower() in genre_aliases for stored in (g.genres or []))
    ]


def filter_by_playtime(
    games: list[Game],
    min_hours: float | None,
    max_hours: float | None,
) -> list[Game]:
    """Games with no recorded playtime are excluded — an unknown length cannot satisfy a range."""
    min_minutes = min_hours * _MINUTES_PER_HOUR if min_hours is not None else None
    max_minutes = max_hours * _MINUTES_PER_HOUR if max_hours is not None else None
    result = []
    for game in games:
        minutes = game.playtime_minutes or 0
        if minutes <= 0:
            continue
        if min_minutes is not None and minutes < min_minutes:
            continue
        if max_minutes is not None and minutes > max_minutes:
            continue
        result.append(game)
    return result


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
            and _valid_score(s)
            for s in (g.source_scores or [])
            if isinstance(s, dict)
        )
    ]


def filter_min_live_sources(games: list[Game], min_live: int) -> list[Game]:
    return [g for g in games if g.live_primary_source_count >= min_live]


def sort_in_memory(games: list[Game], sort: str, direction: str) -> list[Game]:
    reverse = direction == "desc"
    if sort == "review_count":
        return sorted(games, key=lambda g: (_total_review_count(g), g.rank_score, g.metrix_score, -g.id), reverse=reverse)
    source_map = {
        "metacritic_score": "Metacritic",
        "opencritic_score": "OpenCritic",
        "steam_score": "Steam",
    }
    if sort in source_map:
        src = source_map[sort]
        return sorted(games, key=lambda g: (_source_score(g, src), g.rank_score, g.metrix_score, -g.id), reverse=reverse)
    if sort == "title" and direction == "desc":
        return sorted(games, key=lambda g: g.title.lower(), reverse=True)
    if sort == "rank_score":
        return sorted(games, key=lambda g: (g.rank_score, g.metrix_score, g.live_primary_source_count, -g.id), reverse=reverse)
    if sort == "metrix_score":
        return sorted(games, key=lambda g: (g.metrix_score, g.rank_score, g.live_primary_source_count, -g.id), reverse=reverse)
    if sort == "critic_score":
        return sorted(games, key=lambda g: (g.critic_score, g.rank_score, g.metrix_score, -g.id), reverse=reverse)
    if sort == "user_score":
        return sorted(games, key=lambda g: (g.user_score, g.rank_score, g.metrix_score, -g.id), reverse=reverse)
    if sort == "release_year":
        return sorted(games, key=lambda g: (g.release_year, g.rank_score, g.metrix_score, -g.id), reverse=reverse)
    return games
