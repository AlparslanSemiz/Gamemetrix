"""
RAWG search result → Game object creation and metadata application.

Public API:
  parse_rawg_date(value)           -> date
  platform_family(name)            -> str
  rawg_source_scores(meta_score)   -> list[dict]
  game_from_rawg_search(raw_game)  -> Game  (new record)
  apply_rawg_to_game(game, raw)    -> Game  (update existing from search hit)
  apply_rawg_metadata(game, raw)   -> bool  (rich detail enrichment, True if changed)
"""

import re
from datetime import UTC, date, datetime
from urllib.parse import urlparse

from ..content_type import infer_content_type
from ..models import Game
from ..integrations.sync import calculate_metrix_score
from ..integrations.types import normalize_game_modes
from .metadata import clean_game_summary, invalidate_summary_audit, summary_needs_enrichment


def parse_rawg_date(value: str | None) -> date:
    if not value:
        return date(1970, 1, 1)
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date(1970, 1, 1)


def platform_family(platform_name: str) -> str:
    n = platform_name.lower()
    if "playstation" in n:
        return "PlayStation"
    if "xbox" in n:
        return "Xbox"
    if "nintendo" in n or "switch" in n or "wii" in n:
        return "Nintendo"
    if n == "pc" or "windows" in n:
        return "Steam"
    if "mac" in n:
        return "Mac"
    if "linux" in n:
        return "Linux"
    if "ios" in n or "android" in n:
        return "Mobile"
    return platform_name


def rawg_source_scores(metacritic_score: int | None) -> list[dict]:
    if metacritic_score is None:
        return [{"source": "RAWG", "score": 0, "scale": 100, "status": "live",
                 "detail": "RAWG returned no Metacritic score."}]
    return [{"source": "Metacritic", "score": float(metacritic_score), "scale": 100,
             "status": "live", "detail": "Metacritic score via RAWG search cache."}]


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "game"


def _extract_genres(raw_game: dict) -> list[str]:
    return [
        g["name"]
        for g in raw_game.get("genres", [])
        if isinstance(g, dict) and g.get("name")
    ]


def _extract_game_modes(raw_game: dict) -> list[str]:
    """RAWG has no game_modes field — the signal lives in its tags."""
    labels = [
        tag["name"]
        for tag in raw_game.get("tags", [])
        if isinstance(tag, dict) and tag.get("name")
    ]
    return list(normalize_game_modes(labels))


def _extract_platforms_raw(raw_game: dict) -> list[str]:
    return [
        entry["platform"]["name"]
        for entry in raw_game.get("platforms", [])
        if isinstance(entry, dict)
        and isinstance(entry.get("platform"), dict)
        and entry["platform"].get("name")
    ]


def _extract_platforms_normalized(raw_game: dict) -> list[str]:
    return sorted({
        platform_family(entry["platform"]["name"])
        for entry in raw_game.get("platforms", [])
        if isinstance(entry, dict)
        and isinstance(entry.get("platform"), dict)
        and entry["platform"].get("name")
    })


def _extract_screenshots(raw_game: dict) -> list[str]:
    return [
        s["image"]
        for s in (raw_game.get("short_screenshots") or [])
        if isinstance(s, dict) and s.get("image")
    ]


def _extract_system_requirements(raw_game: dict) -> list[dict]:
    return [
        {
            "platform": entry["platform"]["name"],
            "minimum": entry["requirements"].get("minimum") or "",
            "recommended": entry["requirements"].get("recommended") or "",
        }
        for entry in (raw_game.get("platforms") or [])
        if isinstance(entry, dict)
        and isinstance(entry.get("platform"), dict)
        and isinstance(entry.get("requirements"), dict)
        and (entry["requirements"].get("minimum") or entry["requirements"].get("recommended"))
    ]


def _clean_website_url(value: str | None) -> str | None:
    if not value:
        return None
    url = value.strip()
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url[:500]


def _compact_related(raw_game: dict) -> dict:
    released = raw_game.get("released")
    return {
        "id": raw_game.get("id"),
        "title": raw_game.get("name") or "Untitled Game",
        "slug": raw_game.get("slug"),
        "release_date": released,
        "release_year": parse_rawg_date(released).year if released else None,
        "cover_url": raw_game.get("background_image"),
        "metacritic_score": raw_game.get("metacritic"),
        "rating": raw_game.get("rating"),
        "url": f"https://rawg.io/games/{raw_game.get('slug')}" if raw_game.get("slug") else None,
    }


def game_from_rawg_search(raw_game: dict) -> Game:
    title = raw_game.get("name") or "Untitled Game"
    released = parse_rawg_date(raw_game.get("released"))
    metacritic_score = raw_game.get("metacritic")
    if metacritic_score is not None:
        metacritic_score = int(metacritic_score)

    image_url = raw_game.get("background_image") or ""
    source_scores = rawg_source_scores(metacritic_score)
    metrix_score = calculate_metrix_score(source_scores)
    rawg_id = raw_game.get("id") or _slugify(title)

    game = Game(
        title=title,
        slug=f"{_slugify(title)}-{rawg_id}",
        summary=(
            f"{title} was cached from RAWG search. Full editorial metadata can "
            "be enriched by the broader RAWG import flow."
        ),
        cover_url=image_url,
        release_date=released,
        release_year=released.year,
        official_release_date=released if released.year > 1970 else None,
        metacritic_score=metacritic_score,
        image_url=image_url or None,
        website_url=_clean_website_url(raw_game.get("website")),
        metrix_score=metrix_score,
        critic_score=float(metacritic_score or 0),
        user_score=metrix_score,
        genres=_extract_genres(raw_game) or ["Uncategorized"],
        platforms=_extract_platforms_raw(raw_game) or ["Unknown"],
        source_scores=source_scores,
        screenshots=_extract_screenshots(raw_game),
        system_requirements=_extract_system_requirements(raw_game),
    )
    game.content_type = infer_content_type(game, rawg_game_type=raw_game.get("game_type"))
    return game


def apply_rawg_to_game(game: Game, raw_game: dict) -> Game:
    released = parse_rawg_date(raw_game.get("released"))
    metacritic_score = raw_game.get("metacritic")
    if metacritic_score is not None:
        metacritic_score = int(metacritic_score)

    image_url = raw_game.get("background_image") or ""
    fresh_scores = rawg_source_scores(metacritic_score)
    by_source = {str(s.get("source")): s for s in game.source_scores}
    for score in fresh_scores:
        by_source[str(score.get("source"))] = score
    merged = list(by_source.values())

    game.release_date = released
    game.release_year = released.year
    if released.year > 1970:
        game.official_release_date = released
    game.metacritic_score = metacritic_score
    game.image_url = image_url or None
    game.website_url = _clean_website_url(raw_game.get("website")) or game.website_url
    game.cover_url = image_url or game.cover_url
    game.metrix_score = calculate_metrix_score(merged)
    game.critic_score = float(metacritic_score or 0)
    game.user_score = game.metrix_score
    game.source_scores = merged
    game.content_type = infer_content_type(game, rawg_game_type=raw_game.get("game_type"))
    return game


def apply_rawg_metadata(game: Game, raw_game: dict) -> bool:
    changed = False

    summary = clean_game_summary(raw_game.get("description_raw"), game.title)
    if summary and (summary_needs_enrichment(game) or len(summary) > len(game.summary)):
        game.summary = summary
        invalidate_summary_audit(game)
        changed = True

    image_url = raw_game.get("background_image")
    if image_url and (not game.cover_url or "steam/apps" not in game.cover_url):
        game.cover_url = image_url
        game.image_url = image_url
        changed = True

    website_url = _clean_website_url(raw_game.get("website"))
    if website_url and game.website_url != website_url:
        game.website_url = website_url
        changed = True

    released = parse_rawg_date(raw_game.get("released"))
    if released.year > 1970 and (game.release_year == 1970 or game.release_date.year == 1970):
        game.release_date = released
        game.release_year = released.year
        changed = True

    genres = _extract_genres(raw_game)
    if genres and (not game.genres or game.genres in (["Steam"], ["Uncategorized"], ["Deal", "PC"])):
        game.genres = genres[:4]
        changed = True

    game_modes = _extract_game_modes(raw_game)
    if game_modes and not game.game_modes:
        game.game_modes = game_modes
        changed = True

    platforms = _extract_platforms_normalized(raw_game)
    if platforms and (not game.platforms or game.platforms == ["Unknown"]):
        game.platforms = platforms
        changed = True

    developers = raw_game.get("developers") or []
    if developers and not game.developer:
        dev = developers[0].get("name") if isinstance(developers[0], dict) else None
        if dev:
            game.developer = dev
            changed = True

    publishers = raw_game.get("publishers") or []
    if publishers and not game.publisher:
        pub = publishers[0].get("name") if isinstance(publishers[0], dict) else None
        if pub:
            game.publisher = pub
            changed = True

    meta_score = raw_game.get("metacritic")
    if meta_score is not None:
        _apply_metacritic_score(game, int(meta_score))
        changed = True

    if released.year > 1970 and game.official_release_date != released:
        game.official_release_date = released
        changed = True

    screenshots = _extract_screenshots(raw_game)
    if screenshots and not getattr(game, "screenshots", None):
        game.screenshots = screenshots
        changed = True

    sysreqs = _extract_system_requirements(raw_game)
    if sysreqs and not getattr(game, "system_requirements", None):
        game.system_requirements = sysreqs
        changed = True

    game.content_type = infer_content_type(game, rawg_game_type=raw_game.get("game_type"))
    return changed


def apply_rawg_related(game: Game, additions: list[dict], similar: list[dict]) -> bool:
    changed = False
    dlcs = [_compact_related(item) for item in additions if isinstance(item, dict)]
    related = [_compact_related(item) for item in similar if isinstance(item, dict)]

    if dlcs and not getattr(game, "dlcs", None):
        game.dlcs = dlcs[:12]
        changed = True
    if related and not getattr(game, "similar_games", None):
        game.similar_games = related[:12]
        changed = True

    return changed


def game_from_rawg_list(raw_game: dict) -> Game:
    """Create a Game from a RAWG paginated list result (bulk import, may include developer/publisher)."""
    title = raw_game.get("name") or "Untitled Game"
    released = parse_rawg_date(raw_game.get("released"))
    metacritic_score = raw_game.get("metacritic")
    if metacritic_score is not None:
        metacritic_score = int(metacritic_score)

    rawg_rating = float(raw_game.get("rating") or 0)
    if rawg_rating > 0 and metacritic_score is None:
        source_scores: list[dict] = [{
            "source": "RAWG", "score": round(rawg_rating * 20, 1),
            "scale": 100, "status": "live",
        }]
    else:
        source_scores = rawg_source_scores(metacritic_score)

    developers = raw_game.get("developers") or []
    developer: str | None = (
        developers[0].get("name") if developers and isinstance(developers[0], dict) else None
    )
    publishers = raw_game.get("publishers") or []
    publisher: str | None = (
        publishers[0].get("name") if publishers and isinstance(publishers[0], dict) else None
    )

    metrix_score = calculate_metrix_score(source_scores)
    rawg_id = raw_game.get("id") or _slugify(title)
    image_url = raw_game.get("background_image") or ""

    game = Game(
        title=title,
        slug=f"{_slugify(title)}-{rawg_id}",
        summary=f"{title} is part of the imported RAWG catalog.",
        cover_url=image_url,
        release_date=released,
        release_year=released.year,
        official_release_date=released if released.year > 1970 else None,
        metacritic_score=metacritic_score,
        image_url=image_url or None,
        website_url=_clean_website_url(raw_game.get("website")),
        metrix_score=metrix_score,
        critic_score=float(metacritic_score or 0),
        user_score=round(rawg_rating * 20, 1),
        genres=_extract_genres(raw_game) or ["Uncategorized"],
        platforms=_extract_platforms_normalized(raw_game) or ["Unknown"],
        source_scores=source_scores,
        developer=developer,
        publisher=publisher,
        screenshots=_extract_screenshots(raw_game),
        system_requirements=_extract_system_requirements(raw_game),
    )
    game.content_type = infer_content_type(game, rawg_game_type=raw_game.get("game_type"))
    return game


def _apply_metacritic_score(game: Game, metacritic_score: int) -> None:
    game.metacritic_score = metacritic_score
    by_source = {str(s.get("source")): s for s in game.source_scores}
    by_source["Metacritic"] = {
        "source": "Metacritic",
        "score": float(metacritic_score),
        "scale": 100,
        "status": "live",
        "detail": "Metacritic score via RAWG metadata enrichment.",
        "refreshed_at": datetime.now(UTC).isoformat(),
    }
    game.source_scores = list(by_source.values())
    game.metrix_score = calculate_metrix_score(game.source_scores)
    if game.critic_score <= 0:
        game.critic_score = float(metacritic_score)
