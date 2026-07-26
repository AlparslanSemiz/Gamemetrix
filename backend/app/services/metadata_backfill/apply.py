"""Writing a NormalizedGame's fields onto an existing Game, gap by gap.

Only fills genuine gaps: an existing non-placeholder value is never overwritten
(except cover art when `prefer_cover` is set for a trusted, higher-quality source).
"""

from __future__ import annotations

from ...integrations.types import NormalizedGame
from ...models import Game
from ..metadata import clean_game_summary, invalidate_summary_audit, summary_needs_enrichment
from .sanitize import (
    GENERIC_GENRES,
    GENERIC_PLATFORMS,
    MAX_SCREENSHOTS,
    is_missing_cover,
    merge_unique,
    safe_url,
    system_requirements_need_repair,
    titles_match_game,
    tupled,
)

_MAX_NAME_LENGTH = 200
_MAX_GENRES = 6
_MAX_PLATFORMS = 12
_MAX_REQUIREMENTS = 12
_EARLIEST_MEANINGFUL_YEAR = 1970


def apply_normalized_game(
    game: Game,
    result: NormalizedGame,
    *,
    trusted: bool = False,
    prefer_cover: bool = False,
) -> bool:
    if not trusted and not titles_match_game(game, result):
        return False

    return any([
        _apply_cover(game, result, prefer_cover),
        _apply_summary(game, result),
        _apply_release_dates(game, result),
        _apply_credits(game, result),
        _apply_taxonomy(game, result),
        _apply_website(game, result),
        _apply_screenshots(game, result),
        _apply_system_requirements(game, result),
    ])


def _apply_cover(game: Game, result: NormalizedGame, prefer_cover: bool) -> bool:
    cover_url = safe_url(result.cover_url)
    if not cover_url or not (prefer_cover or is_missing_cover(game.cover_url)):
        return False
    if game.cover_url == cover_url:
        return False
    game.cover_url = cover_url
    game.image_url = cover_url
    return True


def _apply_summary(game: Game, result: NormalizedGame) -> bool:
    summary = clean_game_summary(result.summary, game.title)
    if not summary or not (summary_needs_enrichment(game) or len(summary) > len(game.summary)):
        return False
    game.summary = summary
    invalidate_summary_audit(game)
    return True


def _apply_release_dates(game: Game, result: NormalizedGame) -> bool:
    if not result.release_date or result.release_date.year <= _EARLIEST_MEANINGFUL_YEAR:
        return False
    changed = False
    if game.release_year == _EARLIEST_MEANINGFUL_YEAR or game.release_date.year == _EARLIEST_MEANINGFUL_YEAR:
        game.release_date = result.release_date
        game.release_year = result.release_date.year
        changed = True
    if game.official_release_date is None:
        game.official_release_date = result.release_date
        changed = True
    return changed


def _apply_credits(game: Game, result: NormalizedGame) -> bool:
    changed = False
    if result.developer and not game.developer:
        game.developer = result.developer[:_MAX_NAME_LENGTH]
        changed = True
    if result.publisher and not game.publisher:
        game.publisher = result.publisher[:_MAX_NAME_LENGTH]
        changed = True
    if result.franchise and game.franchise != result.franchise[:_MAX_NAME_LENGTH]:
        game.franchise = result.franchise[:_MAX_NAME_LENGTH]
        changed = True
    return changed


def _apply_taxonomy(game: Game, result: NormalizedGame) -> bool:
    changed = False
    if result.genres and tupled(game.genres) in GENERIC_GENRES:
        game.genres = result.genres[:_MAX_GENRES]
        changed = True
    if result.game_modes and not game.game_modes:
        game.game_modes = result.game_modes
        changed = True
    if result.platforms and tupled(game.platforms) in GENERIC_PLATFORMS:
        game.platforms = result.platforms[:_MAX_PLATFORMS]
        changed = True
    return changed


def _apply_website(game: Game, result: NormalizedGame) -> bool:
    raw_website = result.raw.get("website")
    website = safe_url(
        result.external_url if result.source != "Steam"
        else raw_website if isinstance(raw_website, str)
        else None
    )
    if not website or game.website_url:
        return False
    game.website_url = website
    return True


def _apply_screenshots(game: Game, result: NormalizedGame) -> bool:
    raw_screenshots = result.raw.get("screenshots", [])
    if not isinstance(raw_screenshots, list):
        return False
    screenshots = [
        safe
        for url in raw_screenshots[:MAX_SCREENSHOTS]
        if isinstance(url, str) and (safe := safe_url(url)) is not None
    ]
    if not screenshots or game.screenshots:
        return False
    game.screenshots = merge_unique(game.screenshots, screenshots, MAX_SCREENSHOTS)
    return True


def _apply_system_requirements(game: Game, result: NormalizedGame) -> bool:
    raw_requirements = result.raw.get("system_requirements", [])
    if not isinstance(raw_requirements, list):
        return False
    requirements = [row for row in raw_requirements[:_MAX_REQUIREMENTS] if isinstance(row, dict)]
    if not requirements or not system_requirements_need_repair(game.system_requirements):
        return False
    game.system_requirements = requirements
    return True
