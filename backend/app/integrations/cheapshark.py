from datetime import UTC, date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Game, infer_content_type
from ..services.deduplication import find_existing_duplicate, merge_game_data
from .rate_limiter import get_rate_limiter
from .sync import calculate_metrix_score


CHEAPSHARK_DEALS_URL = "https://www.cheapshark.com/api/1.0/deals"
STEAM_APP_PATTERN = "/steam/apps/"

_HTTP_TIMEOUT = 20
_DEFAULT_SCORE_FLOOR = 60.0


def _slugify(value: str, suffix: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
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


def _source_scores(deal: dict[str, str | float | int]) -> list[dict[str, str | float | int]]:
    scores: list[dict[str, str | float | int]] = []

    metacritic = float(deal.get("metacriticScore") or 0)
    if metacritic > 0:
        scores.append({
            "source": "Metacritic",
            "score": metacritic,
            "scale": 100,
            "status": "live",
        })

    steam_rating = float(deal.get("steamRatingPercent") or 0)
    steam_review_count = int(deal.get("steamRatingCount") or 0)
    if steam_rating > 0:
        scores.append({
            "source": "Steam",
            "score": steam_rating,
            "scale": 100,
            "status": "live",
            "review_count": steam_review_count,
            "detail": (
                f"{deal.get('steamRatingText') or 'Steam rating'} "
                f"({steam_review_count:,} reviews) via CheapShark"
            ),
        })

    deal_rating = float(deal.get("dealRating") or 0)
    if deal_rating > 0:
        scores.append({
            "source": "CheapShark",
            "score": round(deal_rating * 10, 1),
            "scale": 100,
            "status": "live",
            "detail": f"Current deal ${deal.get('salePrice')} from store {deal.get('storeID')}",
        })

    return scores or [{
        "source": "CheapShark",
        "score": _DEFAULT_SCORE_FLOOR,
        "scale": 100,
        "status": "live",
    }]


def _hd_cover(deal: dict[str, str | float | int]) -> str:
    thumb = deal.get("thumb") or ""
    if "steamstatic.com" in thumb and STEAM_APP_PATTERN in thumb:
        parts = thumb.split(STEAM_APP_PATTERN)
        if len(parts) == 2:
            app_id = parts[1].split("/")[0]
            return f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"
    return thumb


def _to_game(deal: dict[str, str | float | int]) -> Game:
    title = deal.get("title") or "Untitled Deal"
    released = _date_from_unix(deal.get("releaseDate"))
    source_scores = _source_scores(deal)
    metrix_score = calculate_metrix_score(source_scores)
    rating_count = int(deal.get("steamRatingCount") or 0)
    rating_text = deal.get("steamRatingText") or "not listed"

    summary = (
        f"{title} is a PC game with live store and Steam audience data. "
        f"Current tracked sale price is ${deal.get('salePrice')} "
        f"(normal: ${deal.get('normalPrice')}). "
        f"Steam user sentiment is {rating_text} across {rating_count:,} ratings."
    )

    game = Game(
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
    game.content_type = infer_content_type(game)
    return game


async def import_cheapshark_deals(
    db: Session,
    target: int = 300,
    page_size: int = 60,
) -> dict[str, int]:
    imported = 0
    skipped = 0
    page = 0
    seen_slugs: set[str] = set()
    headers = {"User-Agent": "GameMetrix/0.1 (local-development)"}

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=headers) as client:
        while imported < target:
            if not await get_rate_limiter().acquire("CheapShark"):
                break
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
                if game.slug in seen_slugs:
                    skipped += 1
                    continue
                seen_slugs.add(game.slug)

                with db.no_autoflush:
                    existing = db.scalar(select(Game).where(Game.slug == game.slug))
                if existing:
                    merge_game_data(existing, game)
                    db.add(existing)
                    skipped += 1
                    continue

                existing = find_existing_duplicate(db, game)
                if existing:
                    merge_game_data(existing, game)
                    db.add(existing)
                    skipped += 1
                    continue

                db.add(game)
                try:
                    db.commit()
                    imported += 1
                except IntegrityError:
                    db.rollback()
                    skipped += 1

            page += 1

    return {"imported": imported, "skipped": skipped}
