from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Game, infer_content_type


FREE_TO_GAME_URL = "https://www.freetogame.com/api/games"

_HTTP_TIMEOUT = 20
_SCORE_POPULAR_GENRE = 72.0
_SCORE_DEFAULT = 68.0
_POPULAR_GENRES = {"Shooter", "MMORPG", "MOBA"}


def _slugify(value: str, suffix: int) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    slug = "-".join(part for part in slug.split("-") if part)
    return f"{slug}-{suffix}"


def _release_date(value: str | None) -> date:
    if not value:
        return date(1970, 1, 1)
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date(1970, 1, 1)


def _platforms(value: str | None) -> list[str]:
    if not value:
        return ["PC"]
    normalized = value.lower()
    platforms: list[str] = []
    if "pc" in normalized or "windows" in normalized:
        platforms.extend(["PC", "Steam"])
    if "browser" in normalized or "web" in normalized:
        platforms.append("Browser")
    return sorted(set(platforms or [value]))


def _score_for(genre: str | None) -> float:
    # FreeToGame has no critic/user scores; assign slightly higher floor to popular genres.
    if genre in _POPULAR_GENRES:
        return _SCORE_POPULAR_GENRE
    return _SCORE_DEFAULT


def _to_game(raw_game: dict[str, str | int]) -> Game:
    title = raw_game.get("title") or "Untitled Game"
    released = _release_date(raw_game.get("release_date"))
    genre = raw_game.get("genre") or "Free-to-play"
    score = _score_for(genre)
    platform_values = _platforms(raw_game.get("platform"))
    developer: str | None = raw_game.get("developer") or None
    publisher: str | None = raw_game.get("publisher") or None

    dev_text = raw_game.get("developer") or "Unknown developer"
    pub_text = raw_game.get("publisher") or "Unknown publisher"
    summary = (
        f"{raw_game.get('short_description') or title} "
        f"Developer: {dev_text}. Publisher: {pub_text}. "
        "Free-to-play availability and platform data are tracked from the public catalog."
    )

    game = Game(
        title=title,
        slug=_slugify(title, int(raw_game["id"])),
        summary=summary,
        cover_url=raw_game.get("thumbnail") or "",
        release_date=released,
        release_year=released.year,
        metrix_score=score,
        critic_score=0,
        user_score=score,
        genres=[genre],
        platforms=platform_values,
        developer=developer,
        publisher=publisher,
        source_scores=[{
            "source": "FreeToGame",
            "score": score,
            "scale": 100,
            "status": "live",
            "detail": raw_game.get("game_url") or raw_game.get("freetogame_profile_url") or "",
        }],
    )
    game.content_type = infer_content_type(game)
    return game


async def import_free_to_game_games(db: Session, target: int = 500) -> dict[str, int]:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        response = await client.get(FREE_TO_GAME_URL)
        response.raise_for_status()

    imported = 0
    skipped = 0

    for raw_game in response.json()[:target]:
        game = _to_game(raw_game)
        existing = db.scalar(select(Game).where(Game.slug == game.slug))
        if existing:
            skipped += 1
            continue

        db.add(game)
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped}
