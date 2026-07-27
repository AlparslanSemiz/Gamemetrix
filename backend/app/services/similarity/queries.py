"""Candidate retrieval: a small, fixed number of DB queries per request.

A top-ranked global pool alone buries niche titles, so genre-, series-, signal-
and developer-targeted pools are unioned in before anything is scored.
"""

import json
from datetime import date

from sqlalchemy import Select, or_, select, text
from sqlalchemy.orm import Session, defer, noload

from ...models import Game
from .ranking import rank_similar_games
from .signals import meaningful_genres, normalize_signal, series_key_for_title, text_signals
from .taxonomy import (
    GENRE_WEIGHTS,
    IGNORED_GENRES,
    PLATFORM_GENRES,
    SIGNAL_SEARCH_PRIORITY,
    SIGNAL_SEARCH_TERMS,
    SIGNAL_SEARCH_TRIGGERS,
)

SIMILAR_CANDIDATE_POOL = 320
SIMILAR_GENRE_POOL = 140
SIMILAR_DEVELOPER_POOL = 40
SIMILAR_SERIES_POOL = 40
SIMILAR_SIGNAL_POOL = 70
SERIES_CANDIDATE_POOL = 80

_MAX_SEARCH_GENRES = 4
_MAX_SEARCH_SIGNALS = 3
_DEFAULT_SEARCH_GENRE_WEIGHT = 10
_MIN_SERIES_PATTERN_LENGTH = 5

# A series key's first token must be at least this long to identify a franchise
# on its own ("persona", "witcher", "bioshock"). Shorter first tokens ("god",
# "dark", "mass") are too generic, so those fall back to full-key equality —
# which still works because numerals/editions are already stripped from keys
# ("Dark Souls III" and "Dark Souls II" both normalize to "dark souls").
_FRANCHISE_MIN_FIRST_TOKEN = 6

# Containment rather than a lateral expansion: `ix_games_genres_gin` indexes the
# `genres::jsonb` cast, and only `@>` can use it. Expanding the array per row meant
# a rare genre ("FPS") scanned the whole table before its LIMIT filled — 15s for 8
# rows. Semantics are unchanged: both match an exact element string.
_GENRE_MATCH_SQL = "games.genres::jsonb @> CAST(:genre AS jsonb)"


# Ranking never reads these, and a candidate pool runs into four figures, so
# leaving them in the SELECT means parsing megabytes of JSON to pick ten rows.
_UNRANKED_COLUMNS = (
    Game.screenshots,
    Game.system_requirements,
    Game.dlcs,
    Game.similar_games,
    Game.source_scores,
)


def _base_query(limit: int) -> Select[tuple[Game]]:
    return (
        select(Game)
        .options(noload(Game.price_snapshots), *(defer(column) for column in _UNRANKED_COLUMNS))
        .where(Game.content_type == "game")
        .order_by(Game.rank_score.desc())
        .limit(limit)
    )


def games_by_slugs(db: Session, slugs: list[str]) -> list[Game]:
    """Re-select cached related-game slugs into the caller's session, order preserved."""
    if not slugs:
        return []
    rows = db.scalars(
        select(Game)
        .options(noload(Game.price_snapshots), *(defer(column) for column in _UNRANKED_COLUMNS))
        .where(Game.slug.in_(slugs))
    ).all()
    by_slug = {game.slug: game for game in rows}
    return [by_slug[slug] for slug in slugs if slug in by_slug]


def find_similar_games(db: Session, source: Game, display_limit: int = 10) -> list[Game]:
    by_slug: dict[str, Game] = {}
    for statement in _candidate_queries(source):
        for game in db.scalars(statement):
            if game.id != source.id:
                by_slug[game.slug] = game
    return rank_similar_games(source, list(by_slug.values()), display_limit)


def _candidate_queries(source: Game) -> list[Select[tuple[Game]]]:
    queries = [_base_query(SIMILAR_CANDIDATE_POOL)]
    queries.extend(_genre_queries(source))
    queries.extend(_series_queries(source))
    queries.extend(_signal_queries(source))
    queries.extend(_developer_queries(source))
    return queries


def _genre_queries(source: Game) -> list[Select[tuple[Game]]]:
    return [
        _base_query(SIMILAR_GENRE_POOL)
        .where(text(_GENRE_MATCH_SQL))
        .params(genre=json.dumps([genre]))
        for genre in _search_genres(source)
    ]


def _series_queries(source: Game) -> list[Select[tuple[Game]]]:
    pattern = _series_title_pattern(source)
    if not pattern:
        return []
    return [_base_query(SIMILAR_SERIES_POOL).where(Game.title.ilike(pattern))]


def _signal_queries(source: Game) -> list[Select[tuple[Game]]]:
    queries = []
    for terms in _search_signal_terms(source):
        clauses = []
        for term in terms:
            pattern = f"%{term}%"
            clauses.extend([
                Game.title.ilike(pattern),
                Game.summary.ilike(pattern),
                Game.summary_short.ilike(pattern),
            ])
        queries.append(_base_query(SIMILAR_SIGNAL_POOL).where(or_(*clauses)))
    return queries


def _developer_queries(source: Game) -> list[Select[tuple[Game]]]:
    if not source.developer:
        return []
    return [_base_query(SIMILAR_DEVELOPER_POOL).where(Game.developer == source.developer)]


def _search_genres(source: Game) -> list[str]:
    """Top genres by weight, with platform tags and duplicates dropped."""
    seen: set[str] = set()
    ordered: list[str] = []
    for genre in source.genres:
        normalized = normalize_signal(genre)
        if not normalized or normalized in PLATFORM_GENRES or normalized in IGNORED_GENRES:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(genre)
    ordered.sort(
        key=lambda g: GENRE_WEIGHTS.get(normalize_signal(g), _DEFAULT_SEARCH_GENRE_WEIGHT),
        reverse=True,
    )
    return ordered[:_MAX_SEARCH_GENRES]


def _series_title_pattern(source: Game) -> str | None:
    series = series_key_for_title(source.title)
    if len(series) < _MIN_SERIES_PATTERN_LENGTH:
        return None
    return f"%{'%'.join(series.split())}%"


def _search_signal_terms(source: Game) -> list[list[str]]:
    source_signals = text_signals(source)
    source_genres = set(meaningful_genres(source))
    is_action_flavoured = (
        "action" in source_genres
        or bool({"shooter", "horror", "survival"} & source_signals)
    )
    if not (SIGNAL_SEARCH_TRIGGERS & source_signals and is_action_flavoured):
        return []
    return [
        SIGNAL_SEARCH_TERMS[signal]
        for signal in SIGNAL_SEARCH_PRIORITY
        if signal in source_signals
    ][:_MAX_SEARCH_SIGNALS]


def find_series_games(db: Session, source: Game, limit: int = 8) -> list[Game]:
    """
    Other entries in the source game's franchise, oldest first.

    Authoritative membership comes from IGDB's franchise/collection (`Game.franchise`)
    when present; the title-key heuristic then fills in siblings IGDB has not tagged
    yet, so "Persona 5 Royal" matches "Persona 4 Golden" but not "Personal Trainer".
    """
    matches: dict[int, Game] = {}
    if source.franchise:
        matches.update({game.id: game for game in db.scalars(_franchise_query(source))})

    source_key = series_key_for_title(source.title)
    statement = _series_title_query(source, source_key)
    if statement is not None:
        for game in db.scalars(statement):
            if game.id not in matches and _same_franchise(source_key, series_key_for_title(game.title)):
                matches[game.id] = game

    ordered = sorted(matches.values(), key=lambda g: (g.release_year or 0, g.release_date or date.min))
    return ordered[:limit]


def _franchise_query(source: Game) -> Select[tuple[Game]]:
    return (
        _base_query(SERIES_CANDIDATE_POOL)
        .where(Game.id != source.id)
        .where(Game.franchise == source.franchise)
    )


def _series_title_query(source: Game, source_key: str) -> Select[tuple[Game]] | None:
    if not source_key:
        return None
    first_token = source_key.split()[0]
    pattern = (
        f"%{first_token}%"
        if len(first_token) >= _FRANCHISE_MIN_FIRST_TOKEN
        else _series_title_pattern(source)
    )
    if not pattern:
        return None
    return _base_query(SERIES_CANDIDATE_POOL).where(Game.id != source.id).where(Game.title.ilike(pattern))


def _same_franchise(source_key: str, candidate_key: str) -> bool:
    if not source_key or not candidate_key:
        return False
    if source_key == candidate_key:
        return True
    source_first = source_key.split()[0]
    return (
        source_first == candidate_key.split()[0]
        and len(source_first) >= _FRANCHISE_MIN_FIRST_TOKEN
    )
