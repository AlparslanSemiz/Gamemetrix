from datetime import UTC, date, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..models import Game
from .sync import calculate_metrix_score


CHEAPSHARK_DEALS_URL = "https://www.cheapshark.com/api/1.0/deals"


def _slugify(value: str, suffix: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in value)
    slug = "-".join(part for part in slug.split("-") if part)
    return f"{slug}-{suffix}"


def _date_from_unix(value: str | int | None) -> date:
    try:
        timestamp = int(value or 0)
    except ValueError:
        return date(1970, 1, 1)

    if timestamp <= 0:
        return date(1970, 1, 1)

    return datetime.fromtimestamp(timestamp, tz=UTC).date()


def _source_scores(deal: dict[str, Any]) -> list[dict[str, str | float | int]]:
    scores: list[dict[str, str | float | int]] = []

    metacritic = float(deal.get("metacriticScore") or 0)
    if metacritic > 0:
        scores.append(
            {
                "source": "Metacritic",
                "score": metacritic,
                "scale": 100,
                "status": "live",
            }
        )

    steam_rating = float(deal.get("steamRatingPercent") or 0)
    steam_review_count = int(deal.get("steamRatingCount") or 0)
    if steam_rating > 0:
        scores.append(
            {
                "source": "Steam",
                "score": steam_rating,
                "scale": 100,
                "status": "live",
                "review_count": steam_review_count,
                "detail": f"{deal.get('steamRatingText') or 'Steam rating'} ({steam_review_count:,} reviews) via CheapShark",
            }
        )

    deal_rating = float(deal.get("dealRating") or 0)
    if deal_rating > 0:
        scores.append(
            {
                "source": "CheapShark",
                "score": round(deal_rating * 10, 1),
                "scale": 100,
                "status": "live",
                "detail": f"Current deal ${deal.get('salePrice')} from store {deal.get('storeID')}",
            }
        )

    return scores or [{"source": "CheapShark", "score": 60, "scale": 100, "status": "live"}]


def _hd_cover(deal: dict[str, Any]) -> str:
    """Upgrade thumb URL to a full-size Steam header image when possible."""
    thumb = deal.get("thumb") or ""
    # CheapShark thumb pattern: https://cdn.akamai.steamstatic.com/steam/apps/{id}/capsule_sm_120.jpg
    if "steamstatic.com/steam/apps/" in thumb:
        parts = thumb.split("/steam/apps/")
        if len(parts) == 2:
            app_id = parts[1].split("/")[0]
            return f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"
    return thumb


def _to_game(deal: dict[str, Any]) -> Game:
    title = deal.get("title") or "Untitled Deal"
    released = _date_from_unix(deal.get("releaseDate"))
    source_scores = _source_scores(deal)
    metrix_score = calculate_metrix_score(source_scores)
    rating_count = int(deal.get("steamRatingCount") or 0)
    rating_text = deal.get("steamRatingText") or "not listed"

    summary = (
        f"{title} is currently available via CheapShark at "
        f"${deal.get('salePrice')} (normal: ${deal.get('normalPrice')}). "
        f"Steam user sentiment: {rating_text} across {rating_count:,} ratings."
    )

    return Game(
        title=title,
        slug=_slugify(title, str(deal.get("gameID") or deal.get("dealID"))),
        summary=summary,
        cover_url=_hd_cover(deal),
        release_date=released,
        release_year=released.year,
        metrix_score=metrix_score,
        critic_score=float(deal.get("metacriticScore") or 0),
        user_score=float(deal.get("steamRatingPercent") or 0),
        genres=["Deal", "PC"],
        platforms=["PC", "Steam"],
        source_scores=source_scores,
        developer=None,
        publisher=None,
    )


async def import_cheapshark_deals(
    db: Session,
    target: int = 300,
    page_size: int = 60,
) -> dict[str, int]:
    imported = 0
    skipped = 0
    page = 0

    headers = {"User-Agent": "GameMetrix/0.1 (local-development)"}

    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        while imported < target:
            response = await client.get(
                CHEAPSHARK_DEALS_URL,
                params={
                    "pageNumber": page,
                    "pageSize": min(page_size, target - imported),
                    "sortBy": "Metacritic",
                    "desc": 1,
                },
            )
            response.raise_for_status()
            deals = response.json()

            if not deals:
                break

            for deal in deals:
                game = _to_game(deal)
                existing = db.query(Game).filter(Game.slug == game.slug).first()
                if existing:
                    skipped += 1
                    continue

                db.add(game)
                imported += 1

            db.commit()
            page += 1

    return {"imported": imported, "skipped": skipped}
