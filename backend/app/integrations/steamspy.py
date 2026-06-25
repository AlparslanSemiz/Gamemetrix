from datetime import date
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..models import Game


STEAMSPY_URL = "https://steamspy.com/api.php"


def _slugify(value: str, suffix: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in value)
    slug = "-".join(part for part in slug.split("-") if part)
    return f"{slug}-{suffix}"


def _score(game: dict[str, Any]) -> float:
    positive = int(game.get("positive") or 0)
    negative = int(game.get("negative") or 0)
    total = positive + negative
    if total == 0:
        return 60.0

    return round((positive / total) * 100, 1)


def _genres(value: str | None) -> list[str]:
    if not value:
        return ["Steam"]

    return [genre.strip() for genre in value.split(",") if genre.strip()][:4] or ["Steam"]


def _to_game(app_id: str, raw_game: dict[str, Any]) -> Game:
    title = raw_game.get("name") or f"Steam App {app_id}"
    score = _score(raw_game)
    owners = raw_game.get("owners") or "unknown ownership"
    average_playtime = int(raw_game.get("average_forever") or 0)
    playtime_text = (
        f"Average recorded playtime is about {round(average_playtime / 60, 1)} hours."
        if average_playtime > 0
        else "Average playtime is not yet available."
    )
    developer = raw_game.get("developer") or "Unknown developer"
    publisher = raw_game.get("publisher") or "Unknown publisher"

    summary = (
        f"{title} is a Steam catalog entry tracked by SteamSpy. "
        f"Developer: {developer}. Publisher: {publisher}. "
        f"Estimated owners: {owners}. {playtime_text}"
    )

    positive = int(raw_game.get("positive") or 0)
    negative = int(raw_game.get("negative") or 0)
    total_reviews = positive + negative

    developer = raw_game.get("developer") or None
    publisher = raw_game.get("publisher") or None

    return Game(
        title=title,
        slug=_slugify(title, app_id),
        summary=summary,
        cover_url=f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg",
        release_date=date(1970, 1, 1),
        release_year=1970,
        metrix_score=score,
        critic_score=0,
        user_score=score,
        genres=_genres(raw_game.get("genre")),
        platforms=["PC", "Steam"],
        developer=developer,
        publisher=publisher,
        playtime_minutes=average_playtime,
        source_scores=[
            {
                "source": "SteamSpy",
                "score": score,
                "scale": 100,
                "status": "live",
                "review_count": total_reviews,
                "detail": f"{positive:,} positive / {negative:,} negative Steam reviews",
            }
        ],
    )


async def import_steamspy_games(db: Session, target: int = 2000) -> dict[str, int]:
    imported = 0
    skipped = 0
    page = 0
    headers = {"User-Agent": "GameMetrix/0.1 (local-development)"}

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        while imported < target:
            response = await client.get(
                STEAMSPY_URL,
                params={"request": "all", "page": page},
            )
            response.raise_for_status()
            payload = response.json()

            if not payload:
                break

            for app_id, raw_game in payload.items():
                if imported >= target:
                    break

                game = _to_game(str(app_id), raw_game)
                existing = db.query(Game).filter(Game.slug == game.slug).first()
                if existing:
                    skipped += 1
                    continue

                db.add(game)
                imported += 1

            db.commit()
            page += 1

    return {"imported": imported, "skipped": skipped}
