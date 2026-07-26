"""Pure deterministic signals that decide which catalog rows need AI review."""

import re

from ...models import Game

_PLACEHOLDER_TITLES = frozenset(
    {"game", "n/a", "new game", "none", "null", "tba", "test", "testing", "unknown", "untitled", "untitled game"}
)
_STRONG_NONGAME_MARKERS: tuple[str, ...] = (
    "soundtrack",
    "original soundtrack",
    " ost ",
    "art book",
    "artbook",
    "asset pack",
    "sound pack",
    "sfx pack",
    "wallpaper",
    "season pass",
    "expansion pass",
    "benchmark",
    "dedicated server",
)
_WEAK_SUMMARY_MARKERS: tuple[str, ...] = (
    "description unavailable",
    "free-to-play availability and platform data are tracked",
    "imported from the igdb",
    "no description available",
    "unknown developer",
    "was imported from the igdb",
)
_MOJIBAKE_MARKERS: tuple[str, ...] = ("â", "Ã", "Â", "ï¿½", "�")
_GENERIC_GENRES = {(), ("Uncategorized",)}
_GENERIC_PLATFORMS = {(), ("Uncategorized",), ("Unknown",)}
_MIN_SUMMARY_CHARS = 40
_HTML_RE = re.compile(r"<(?:br|div|h[1-6]|li|p|span|strong|ul)(?:\s|/?>)", re.IGNORECASE)
_REPEATED_CHAR_RE = re.compile(r"(.)\1{5,}", re.IGNORECASE)
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)


def catalog_quality_signals(
    game: Game,
    duplicate_titles: tuple[str, ...] = (),
) -> list[str]:
    """Return deterministic reasons why this row deserves an AI review."""
    title = (game.title or "").strip()
    summary = (game.summary or "").strip()
    marker_text = f" {title} \n {summary} ".casefold()
    signals: list[str] = []

    if title.casefold() in _PLACEHOLDER_TITLES or len(title) <= 1:
        signals.append("suspicious_title")
    if _URL_RE.search(title) or _REPEATED_CHAR_RE.search(title):
        signals.append("malformed_title")
    # An empty summary is a deterministic metadata gap, not an AI judgment.
    # Keep short non-empty text in review because it can be a placeholder,
    # truncation, or a legitimate compact description.
    if summary and len(summary) < _MIN_SUMMARY_CHARS:
        signals.append("weak_summary")
    if _HTML_RE.search(summary):
        signals.append("raw_html_summary")
    if any(marker.casefold() in summary.casefold() for marker in _WEAK_SUMMARY_MARKERS):
        signals.append("placeholder_summary")
    if any(marker in title or marker in summary for marker in _MOJIBAKE_MARKERS):
        signals.append("encoding_corruption")
    if any(marker in marker_text for marker in _STRONG_NONGAME_MARKERS):
        signals.append("non_game_marker")
    if duplicate_titles:
        signals.append("summary_shared_with_other_titles")

    genres = tuple(game.genres or ())
    platforms = tuple(game.platforms or ())
    if genres in _GENERIC_GENRES and platforms in _GENERIC_PLATFORMS and not game.developer:
        signals.append("missing_core_metadata")
    if game.release_year == 1970 and (
        "weak_summary" in signals or "placeholder_summary" in signals or "missing_core_metadata" in signals
    ):
        signals.append("unknown_release_with_weak_metadata")
    if _has_malformed_json_fields(game):
        signals.append("malformed_structured_metadata")

    return list(dict.fromkeys(signals))


def _has_malformed_json_fields(game: Game) -> bool:
    typed_fields: tuple[tuple[object, type], ...] = (
        (game.genres, str),
        (game.platforms, str),
        (game.source_scores, dict),
    )
    return any(
        not isinstance(values, list) or any(not isinstance(item, expected) for item in values)
        for values, expected in typed_fields
    )
