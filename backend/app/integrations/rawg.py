import os
import re
from datetime import date
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..models import Game
from .sync import calculate_metrix_score


RAWG_BASE_URL = "https://api.rawg.io/api"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "game"


def _parse_date(value: str | None) -> date:
    if not value:
        return date(1970, 1, 1)

    try:
        return date.fromisoformat(value)
    except ValueError:
        return date(1970, 1, 1)


def _platform_family(platform_name: str) -> str:
    normalized = platform_name.lower()
    if "playstation" in normalized:
        return "PlayStation"
    if "xbox" in normalized:
        return "Xbox"
    if "nintendo" in normalized or "switch" in normalized or "wii" in normalized:
        return "Nintendo"
    if "pc" == normalized or "windows" in normalized:
        return "Steam"
    if "mac" in normalized:
        return "Mac"
    if "linux" in normalized:
        return "Linux"
    if "ios" in normalized or "android" in normalized:
        return "Mobile"
    return platform_name


def _source_scores(raw_game: dict[str, Any]) -> list[dict[str, str | float | int]]:
    scores: list[dict[str, str | float | int]] = []

    metacritic = raw_game.get("metacritic")
    if metacritic:
        scores.append(
            {
                "source": "Metacritic",
                "score": float(metacritic),
                "scale": 100,
                "status": "live",
            }
        )

    rawg_rating = raw_game.get("rating")
    if rawg_rating:
        scores.append(
            {
                "source": "RAWG",
                "score": round(float(rawg_rating) * 20, 1),
                "scale": 100,
                "status": "live",
            }
        )

    return scores or [{"source": "RAWG", "score": 0, "scale": 100, "status": "live"}]


def _game_from_rawg(raw_game: dict[str, Any]) -> Game:
    title = raw_game.get("name") or "Untitled Game"
    released = _parse_date(raw_game.get("released"))
    source_scores = _source_scores(raw_game)

    genres = [genre["name"] for genre in raw_game.get("genres", []) if genre.get("name")]
    platforms = sorted(
        {
            _platform_family(platform["platform"]["name"])
            for platform in raw_game.get("platforms", [])
            if platform.get("platform", {}).get("name")
        }
    )

    summary = raw_game.get("description_raw") or (
        f"{title} is part of the imported RAWG catalog. Detailed editorial "
        "description can be enriched from RAWG detail or IGDB once API "
        "credentials are configured."
    )

    metrix_score = calculate_metrix_score(source_scores)

    # RAWG list endpoint returns minimal developer info; detail endpoint has full data.
    developers = raw_game.get("developers") or []
    developer = developers[0]["name"] if developers and developers[0].get("name") else None
    publishers = raw_game.get("publishers") or []
    publisher = publishers[0]["name"] if publishers and publishers[0].get("name") else None

    return Game(
        title=title,
        slug=f"{_slugify(title)}-{raw_game.get('id')}",
        summary=summary,
        cover_url=raw_game.get("background_image") or "",
        release_date=released,
        release_year=released.year,
        metrix_score=metrix_score,
        critic_score=metrix_score,
        user_score=round(float(raw_game.get("rating") or 0) * 20, 1),
        genres=genres or ["Uncategorized"],
        platforms=platforms or ["Unknown"],
        source_scores=source_scores,
        developer=developer,
        publisher=publisher,
    )


async def import_rawg_games(db: Session, target: int = 2000, page_size: int = 40) -> dict[str, int]:
    api_key = os.getenv("RAWG_API_KEY")
    if not api_key:
        raise RuntimeError("RAWG_API_KEY is not configured.")

    imported = 0
    skipped = 0
    page = 1

    async with httpx.AsyncClient(timeout=20) as client:
      while imported < target:
          response = await client.get(
              f"{RAWG_BASE_URL}/games",
              params={
                  "key": api_key,
                  "page": page,
                  "page_size": min(page_size, target - imported),
                  "ordering": "-metacritic,-rating",
              },
          )
          response.raise_for_status()
          payload = response.json()
          results = payload.get("results", [])

          if not results:
              break

          for raw_game in results:
              game = _game_from_rawg(raw_game)
              existing = db.query(Game).filter(Game.slug == game.slug).first()
              if existing:
                  skipped += 1
                  continue

              db.add(game)
              imported += 1

          db.commit()
          page += 1

    return {"imported": imported, "skipped": skipped}
