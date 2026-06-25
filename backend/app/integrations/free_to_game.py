from datetime import date
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..models import Game


FREE_TO_GAME_URL = "https://www.freetogame.com/api/games"


def _slugify(value: str, suffix: int) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in value)
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


def _score_for(game: dict[str, Any]) -> float:
    # FreeToGame does not expose critic/user scores. Keep imported games visible
    # without pretending we have authoritative ratings.
    if game.get("genre") in {"Shooter", "MMORPG", "MOBA"}:
        return 72.0
    return 68.0


def _to_game(raw_game: dict[str, Any]) -> Game:
    title = raw_game.get("title") or "Untitled Game"
    released = _release_date(raw_game.get("release_date"))
    score = _score_for(raw_game)
    genre = raw_game.get("genre") or "Free-to-play"
    platform_values = _platforms(raw_game.get("platform"))

    developer = raw_game.get("developer") or "Unknown developer"
    publisher = raw_game.get("publisher") or "Unknown publisher"
    summary = (
        f"{raw_game.get('short_description') or title} "
        f"Developer: {developer}. Publisher: {publisher}. "
        "Imported from FreeToGame, a public free-to-play games catalog."
    )

    return Game(
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
        source_scores=[
            {
                "source": "FreeToGame",
                "score": score,
                "scale": 100,
                "status": "live",
                "detail": raw_game.get("game_url") or raw_game.get("freetogame_profile_url") or "",
            }
        ],
    )


async def import_free_to_game_games(db: Session, target: int = 500) -> dict[str, int]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(FREE_TO_GAME_URL)
        response.raise_for_status()

    imported = 0
    skipped = 0

    for raw_game in response.json()[:target]:
        game = _to_game(raw_game)
        existing = db.query(Game).filter(Game.slug == game.slug).first()
        if existing:
            skipped += 1
            continue

        db.add(game)
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped}
