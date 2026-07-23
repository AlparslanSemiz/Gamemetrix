"""Building the per-source fetch plan for a refresh.

Each source is gated in the same order: cache hit → configured → budget headroom
→ budget acquire → fetch. Any gate that fails yields an `unavailable` score
rather than raising, so one dead provider never fails a whole refresh.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import timedelta

from ...config import get_settings
from ...models import Game
from ..igdb import get_igdb_score
from ..opencritic import get_opencritic_score
from ..rate_limiter import get_rate_limiter
from ..rawg_score import get_rawg_metacritic_score, get_rawg_rating_score
from ..steam import extract_steam_app_id, get_steam_score
from ..steamspy import get_steamspy_score
from ..types import ExternalScore
from .cache import cached_score
from .constants import EARLIEST_MEANINGFUL_YEAR, RAWG_CACHE_TTL
from .values import score_value

_DEFAULT_BUDGET_SOURCE = object()
_OPENCRITIC_DEFAULT_REQUESTS = 2


def _unavailable(source: str, detail: str) -> ExternalScore:
    return ExternalScore(source=source, score=0, status="unavailable", detail=detail)


async def resolve_score(
    source: str,
    cached: ExternalScore | None,
    fetch: Callable[[], Awaitable[ExternalScore]],
    *,
    budget_source: str | None | object = _DEFAULT_BUDGET_SOURCE,
    required_requests: int | None = None,
) -> ExternalScore:
    if cached:
        return cached
    if budget_source is _DEFAULT_BUDGET_SOURCE:
        budget_source = source
    if budget_source is not None and not source_configured(source):
        return _unavailable(source, f"{source} is not configured.")

    if required_requests is None:
        required_requests = _OPENCRITIC_DEFAULT_REQUESTS if source == "OpenCritic" else 1
    if budget_source is not None:
        limiter = get_rate_limiter()
        if limiter.remaining(budget_source) < required_requests:
            return _unavailable(
                source, f"{source} request budget is too low for a complete lookup."
            )
        if not await limiter.acquire(budget_source):
            return _unavailable(
                source,
                f"{source} daily request budget exhausted — will retry in next refresh cycle",
            )
    try:
        return await fetch()
    except Exception as error:
        return _unavailable(source, f"{source} request failed ({type(error).__name__}).")


def source_configured(source: str) -> bool:
    cfg = get_settings()
    if source in {"Metacritic", "RAWG"}:
        return cfg.rawg_configured()
    if source == "OpenCritic":
        return cfg.opencritic_configured()
    if source == "IGDB":
        return cfg.igdb_configured()
    return True


def _wants_source(requested: set[str] | None, source: str) -> bool:
    return requested is None or source in requested


def _fetch_cached_score(
    game: Game,
    source: str,
    *,
    force: bool,
    live_only: bool,
    ttl: timedelta | None = None,
) -> ExternalScore | None:
    if force:
        return None
    return cached_score(game.source_scores, source, ttl, live_only=live_only)


def _numeric_external_id(external_ids: Mapping[str, str], source: str) -> int | None:
    value = external_ids.get(source, "")
    return int(value) if value.isdigit() and int(value) > 0 else None


def _primary_fetch_tasks(
    game: Game,
    external_ids: Mapping[str, str],
    requested: set[str] | None,
    *,
    force: bool,
    live_only_cache: bool,
    release_year: int | None,
) -> list[Awaitable[ExternalScore]]:
    def cached(source: str, ttl: timedelta | None = None) -> ExternalScore | None:
        return _fetch_cached_score(game, source, force=force, live_only=live_only_cache, ttl=ttl)

    tasks: list[Awaitable[ExternalScore]] = []
    if _wants_source(requested, "Metacritic"):
        tasks.append(resolve_score(
            "Metacritic",
            cached("Metacritic", RAWG_CACHE_TTL),
            lambda: get_rawg_metacritic_score(
                game.title,
                cached_value=game.metacritic_score,
                release_year=release_year,
            ),
            budget_source=None if game.metacritic_score is not None else "Metacritic",
        ))
    if _wants_source(requested, "OpenCritic"):
        tasks.append(resolve_score(
            "OpenCritic",
            cached("OpenCritic"),
            lambda: get_opencritic_score(
                game.title,
                release_year=release_year,
                opencritic_id=external_ids.get("OpenCritic"),
            ),
            required_requests=1,
        ))
    if _wants_source(requested, "IGDB"):
        tasks.append(resolve_score(
            "IGDB",
            cached("IGDB"),
            lambda: get_igdb_score(
                game.title,
                release_year=release_year,
                igdb_id=_numeric_external_id(external_ids, "IGDB"),
            ),
        ))
    return tasks


def _steam_fetch_tasks(
    game: Game,
    external_ids: Mapping[str, str],
    requested: set[str] | None,
    *,
    force: bool,
    include_support: bool,
    live_only_cache: bool,
) -> list[Awaitable[ExternalScore]]:
    if not _wants_source(requested, "Steam"):
        return []
    if not game.is_pc_applicable and requested is None:
        return []

    app_id = _numeric_external_id(external_ids, "Steam") or extract_steam_app_id(
        game.slug, game.cover_url, game.image_url
    )
    tasks = [resolve_score(
        "Steam",
        _fetch_cached_score(game, "Steam", force=force, live_only=live_only_cache),
        lambda: get_steam_score(game.slug, game.title, steam_app_id=app_id),
        required_requests=1 if app_id is not None else 2,
    )]
    if include_support and app_id is not None and _wants_source(requested, "SteamSpy"):
        tasks.append(resolve_score(
            "SteamSpy",
            _fetch_cached_score(game, "SteamSpy", force=force, live_only=live_only_cache),
            lambda: get_steamspy_score(app_id),
        ))
    return tasks


def _needs_rawg_fallback(game: Game) -> bool:
    live_primary = {
        str(score.get("source"))
        for score in game.source_scores
        if score.get("status") == "live"
        and score_value(score) is not None
        and str(score.get("source")) in game.applicable_primary_sources
    }
    return len(live_primary) < len(game.applicable_primary_sources)


def _rawg_fallback_tasks(
    game: Game,
    requested: set[str] | None,
    *,
    force: bool,
    live_only_cache: bool,
    release_year: int | None,
) -> list[Awaitable[ExternalScore]]:
    if not _wants_source(requested, "RAWG") or not _needs_rawg_fallback(game):
        return []
    return [resolve_score(
        "RAWG",
        _fetch_cached_score(
            game, "RAWG", force=force, live_only=live_only_cache, ttl=RAWG_CACHE_TTL
        ),
        lambda: get_rawg_rating_score(game.title, release_year=release_year),
    )]


def build_fetch_tasks(
    game: Game,
    *,
    external_ids: Mapping[str, str] | None = None,
    sources: Sequence[str] | None = None,
    force: bool = False,
    include_support: bool = True,
    include_rawg_fallback: bool = True,
) -> list[Awaitable[ExternalScore]]:
    requested = set(sources) if sources is not None else None
    live_only_cache = requested is not None
    external_ids = external_ids or {}
    release_year = (
        game.release_year
        if game.release_year and game.release_year > EARLIEST_MEANINGFUL_YEAR
        else None
    )

    tasks = _primary_fetch_tasks(
        game, external_ids, requested,
        force=force, live_only_cache=live_only_cache, release_year=release_year,
    )
    tasks.extend(_steam_fetch_tasks(
        game, external_ids, requested,
        force=force, include_support=include_support, live_only_cache=live_only_cache,
    ))
    if include_rawg_fallback:
        tasks.extend(_rawg_fallback_tasks(
            game, requested,
            force=force, live_only_cache=live_only_cache, release_year=release_year,
        ))
    return tasks
