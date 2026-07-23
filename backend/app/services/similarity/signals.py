"""Turning a Game's text into comparable signals: genres, keyword groups, series key.

Every function here derives facts from one game in isolation. Nothing here
compares two games — that is `profiles.py`.
"""

import re
from functools import lru_cache

from ...models import Game
from .taxonomy import IGNORED_GENRES, KEYWORD_GROUPS, KNOWN_SERIES_SIGNALS, PLATFORM_GENRES

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_SERIES_STOPWORDS_RE = re.compile(
    r"\b(game of the year|goty|definitive|enhanced|complete|ultimate|deluxe|"
    r"director s cut|remastered|remake|edition|collection)\b"
)
_SERIES_NUMERAL_RE = re.compile(r"\b(i|ii|iii|iv|v|vi|vii|viii|ix|x|\d+)\b")
_SERIES_FILLER_WORDS = {"the", "and", "of", "a", "an", "s"}
_SERIES_KEY_TOKENS = 2

# Series whose key needs a token count other than the default two: "Uncharted 4:
# A Thief's End" must collapse to "uncharted", while "Final Fantasy Tactics" has
# to stay distinct from "Final Fantasy XVI".
_SHORT_SERIES_PREFIXES = (("uncharted",),)
_LONG_SERIES_PREFIXES = (("final", "fantasy"),)
_LONG_SERIES_KEY_TOKENS = 3


def normalize_signal(value: str) -> str:
    return _NON_ALNUM_RE.sub(" ", value.lower()).strip()


@lru_cache(maxsize=4096)
def _phrase_pattern(phrase: str) -> re.Pattern[str] | None:
    normalized = normalize_signal(phrase)
    if not normalized:
        return None
    return re.compile(rf"(^| ){re.escape(normalized)}( |$)")


def has_signal_phrase(text: str, phrase: str) -> bool:
    pattern = _phrase_pattern(phrase)
    return bool(pattern and pattern.search(text))


@lru_cache(maxsize=8192)
def _meaningful_genres_from_tuple(genres: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        g for g in (normalize_signal(genre) for genre in genres)
        if g and g not in PLATFORM_GENRES and g not in IGNORED_GENRES
    )


def meaningful_genres(game: Game) -> list[str]:
    return list(_meaningful_genres_from_tuple(tuple(game.genres or [])))


def _series_tokens(title: str) -> list[str]:
    normalized = normalize_signal(title)
    normalized = _SERIES_STOPWORDS_RE.sub(" ", normalized)
    normalized = _SERIES_NUMERAL_RE.sub(" ", normalized)
    return [t for t in normalized.split(" ") if t and t not in _SERIES_FILLER_WORDS]


def _series_key_length(tokens: list[str]) -> int:
    for prefix in _SHORT_SERIES_PREFIXES:
        if tuple(tokens[: len(prefix)]) == prefix:
            return len(prefix)
    for prefix in _LONG_SERIES_PREFIXES:
        if tuple(tokens[: len(prefix)]) == prefix:
            return _LONG_SERIES_KEY_TOKENS
    return _SERIES_KEY_TOKENS


@lru_cache(maxsize=4096)
def series_key_for_title(title: str) -> str:
    tokens = _series_tokens(title)
    return " ".join(tokens[: _series_key_length(tokens)])


@lru_cache(maxsize=8192)
def _text_signals_cached(
    game_id: int,
    title: str,
    summary_short: str,
    summary: str,
    genres: tuple[str, ...],
) -> frozenset[str]:
    del game_id
    text = normalize_signal(" ".join([title, summary_short, summary, *genres]))
    signals = set(_meaningful_genres_from_tuple(genres))
    for group, words in KEYWORD_GROUPS.items():
        if any(has_signal_phrase(text, word) for word in words):
            signals.add(group)
    signals.update(KNOWN_SERIES_SIGNALS.get(series_key_for_title(title), set()))
    return frozenset(signals)


def text_signals(game: Game) -> frozenset[str]:
    return _text_signals_cached(
        game.id,
        game.title,
        game.summary_short or "",
        game.summary or "",
        tuple(game.genres or []),
    )
