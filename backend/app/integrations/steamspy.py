from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Game, infer_content_type
from .types import ExternalScore


STEAMSPY_URL = "https://steamspy.com/api.php"

_HTTP_TIMEOUT = 30
_SINGLE_TIMEOUT = 10
_DEFAULT_SCORE_FLOOR = 60.0
_SCORE_POPULAR_GENRE = 72.0
_SCORE_DEFAULT = 68.0


async def get_steamspy_score(app_id: int) -> ExternalScore:
    """Fetch positive/negative vote counts for a single Steam app and return a 0-100 score."""
    try:
        async with httpx.AsyncClient(timeout=_SINGLE_TIMEOUT) as client:
            response = await client.get(
                STEAMSPY_URL,
                params={"request": "appdetails", "appid": app_id},
                headers={"User-Agent": "GameMetrix/0.1"},
            )
            response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return ExternalScore(source="SteamSpy", score=0, status="unavailable",
                             detail=f"SteamSpy request failed: {exc}")

    positive = int(data.get("positive") or 0)
    negative = int(data.get("negative") or 0)
    total = positive + negative
    if total == 0:
        return ExternalScore(source="SteamSpy", score=0, status="unavailable",
                             detail="SteamSpy returned no review counts.")

    score = round((positive / total) * 100, 1)
    return ExternalScore(
        source="SteamSpy",
        score=score,
        review_count=total,
        detail=f"SteamSpy: {positive:,} positive / {negative:,} negative ({score:.0f}%)",
        raw={"steam_app_id": app_id},
    )


def _slugify(value: str, suffix: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    slug = "-".join(part for part in slug.split("-") if part)
    return f"{slug}-{suffix}"


def _score(game: dict[str, int | str]) -> float:
    positive = int(game.get("positive") or 0)
    negative = int(game.get("negative") or 0)
    total = positive + negative
    if total == 0:
        return _DEFAULT_SCORE_FLOOR
    return round((positive / total) * 100, 1)


def _genres(value: str | None) -> list[str]:
    if not value:
        return ["Steam"]
    return [genre.strip() for genre in value.split(",") if genre.strip()][:4] or ["Steam"]


def _build_summary(title: str, raw_game: dict[str, int | str]) -> str:
    owners = raw_game.get("owners") or "unknown ownership"
    average_playtime = int(raw_game.get("average_forever") or 0)
    developer = raw_game.get("developer") or "Unknown developer"
    publisher = raw_game.get("publisher") or "Unknown publisher"

    playtime_text = (
        f"Average recorded playtime is about {round(average_playtime / 60, 1)} hours."
        if average_playtime > 0
        else "Average playtime is not yet available."
    )
    genre_text = (raw_game.get("genre") or "PC").split(",")[0].strip().lower() or "pc"
    descriptor = "PC game" if genre_text in {"game", "steam", "pc"} else f"{genre_text} game"
    creator_text = f" developed by {developer}" if developer != "Unknown developer" else ""
    publisher_text = (
        f" and published by {publisher}"
        if publisher != "Unknown publisher" and publisher != developer
        else ""
    )
    return (
        f"{title} is a {descriptor}{creator_text}{publisher_text}. "
        f"It is available on PC through Steam, with estimated ownership around {owners}. "
        f"{playtime_text}"
    )


def _to_game(app_id: str, raw_game: dict[str, int | str]) -> Game:
    title = raw_game.get("name") or f"Steam App {app_id}"
    score = _score(raw_game)
    positive = int(raw_game.get("positive") or 0)
    negative = int(raw_game.get("negative") or 0)
    total_reviews = positive + negative
    average_playtime = int(raw_game.get("average_forever") or 0)
    developer: str | None = raw_game.get("developer") or None
    publisher: str | None = raw_game.get("publisher") or None

    game = Game(
        title=title,
        slug=_slugify(title, app_id),
        summary=_build_summary(title, raw_game),
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
        source_scores=[{
            "source": "SteamSpy",
            "score": score,
            "scale": 100,
            "status": "live",
            "review_count": total_reviews,
            "detail": f"{positive:,} positive / {negative:,} negative Steam reviews",
        }],
    )
    game.content_type = infer_content_type(game)
    return game


async def import_steamspy_games(db: Session, target: int = 2000) -> dict[str, int]:
    imported = 0
    skipped = 0
    page = 0
    headers = {"User-Agent": "GameMetrix/0.1 (local-development)"}

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=headers) as client:
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
                existing = db.scalar(select(Game).where(Game.slug == game.slug))
                if existing:
                    skipped += 1
                    continue

                db.add(game)
                imported += 1

            db.commit()
            page += 1

    return {"imported": imported, "skipped": skipped}
