from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import desc, exists, or_, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..config import get_settings
from ..models import Game, PriceSnapshot
from ..schemas import GameListResponse
from ..services.seo import genre_slug, indexable_genre_facets, sitemap_document


router = APIRouter(tags=["seo"])
CuratedCollection = Literal["home", "linux", "steam-deck", "free", "deals", "year", "genre"]

# A genre only earns a landing page once it has enough indexable games to be
# worth crawling — a three-game page is a thin-content liability, not an asset.
_MIN_GENRE_GAMES = 8


@router.get("/robots.txt", include_in_schema=False)
def robots() -> Response:
    body = "\n".join(
        (
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin",
            "Disallow: /api/",
            "Disallow: /account",
            "Disallow: /login",
            "Disallow: /register",
            "Disallow: /forgot-password",
            "Disallow: /reset-password",
            "Disallow: /verify-email",
            "Disallow: /settings",
            "Disallow: /alerts",
            "Sitemap: https://gamemetrix.me/sitemap.xml",
            "",
        )
    )
    return Response(
        body,
        media_type="text/plain",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap(db: Session = Depends(get_db)) -> Response:
    games = list(
        db.scalars(
            select(Game)
            .where(Game.seo_indexable.is_(True))
            .options(selectinload(Game.price_snapshots))
            .order_by(desc(Game.rank_score), Game.slug)
            .limit(get_settings().SEO_INDEX_LIMIT)
        ).all()
    )
    year_counts: dict[int, int] = {}
    for game in games:
        year_counts[game.release_year] = year_counts.get(game.release_year, 0) + 1
    years = sorted((year for year, count in year_counts.items() if count >= 5), reverse=True)
    fresh_before = datetime.now(UTC) - timedelta(hours=24)

    def fresh_prices(game: Game) -> list[PriceSnapshot]:
        return [
            price for price in game.price_snapshots
            if (price.fetched_at.replace(tzinfo=price.fetched_at.tzinfo or UTC)) >= fresh_before
        ]

    curated_paths: list[str] = []
    linux_count = sum(
        1 for game in games
        if (game.proton_tier or "").lower() in {"native", "platinum", "gold", "silver", "bronze"}
        or any(platform.lower() == "linux" for platform in game.platforms)
    )
    deck_count = sum(
        1 for game in games
        if (game.proton_tier or "").lower() in {"native", "platinum", "gold", "silver"}
    )
    free_count = sum(1 for game in games if any(price.is_free for price in fresh_prices(game)))
    deal_count = sum(
        1 for game in games
        if any(price.is_free or (price.discount_percent or 0) >= 40 for price in fresh_prices(game))
    )
    if linux_count >= 5:
        curated_paths.append("/best/linux-games")
    if deck_count >= 5:
        curated_paths.append("/best/steam-deck-games")
    if free_count >= 5:
        curated_paths.append("/best/free-pc-games")
    if deal_count >= 5:
        curated_paths.append("/deals")
    curated_paths.extend(
        f"/best/{slug}-games" for slug, _, _ in indexable_genre_facets(db, _MIN_GENRE_GAMES)
    )
    return Response(
        sitemap_document(games, years, curated_paths),
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"},
    )


@router.get("/api/seo/genres")
def seo_genres(db: Session = Depends(get_db)) -> dict:
    """Genres that currently qualify for a landing page, newest counts first."""
    return {
        "genres": [
            {"slug": slug, "name": name, "count": count}
            for slug, name, count in indexable_genre_facets(db, _MIN_GENRE_GAMES)
        ],
    }


@router.get("/api/seo/curated/{collection}", response_model=GameListResponse)
def curated_games(
    collection: CuratedCollection,
    year: int | None = Query(default=None, ge=1970, le=2100),
    genre: str | None = Query(default=None, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    limit: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
) -> GameListResponse:
    query = (
        select(Game)
        .where(Game.seo_indexable.is_(True))
        .options(selectinload(Game.price_snapshots))
        .order_by(desc(Game.rank_score), desc(Game.metrix_score), Game.title)
    )
    fresh_before = datetime.now(UTC) - timedelta(hours=24)
    if collection == "year":
        if year is None:
            raise HTTPException(status_code=422, detail="year is required")
        query = query.where(Game.release_year == year)
    elif collection == "free":
        query = query.where(
            exists(
                select(PriceSnapshot.id).where(
                    PriceSnapshot.game_id == Game.id,
                    PriceSnapshot.is_free.is_(True),
                    PriceSnapshot.fetched_at >= fresh_before,
                )
            )
        )
    elif collection == "deals":
        query = query.where(
            exists(
                select(PriceSnapshot.id).where(
                    PriceSnapshot.game_id == Game.id,
                    PriceSnapshot.fetched_at >= fresh_before,
                    or_(
                        PriceSnapshot.is_free.is_(True),
                        PriceSnapshot.discount_percent >= 40,
                    ),
                )
            )
        )

    if collection == "genre":
        if genre is None:
            raise HTTPException(status_code=422, detail="genre is required")
        facets = {slug: display for slug, display, _ in indexable_genre_facets(db, _MIN_GENRE_GAMES)}
        display_name = facets.get(genre)
        if display_name is None:
            raise HTTPException(status_code=404, detail="Unknown genre")

    candidates = list(db.scalars(query.limit(400)).unique().all())
    if collection == "genre" and genre is not None:
        candidates = [
            game for game in candidates
            if any(genre_slug(str(name)) == genre for name in (game.genres or []))
        ]
    elif collection == "linux":
        candidates = [
            game for game in candidates
            if (game.proton_tier or "").lower() in {"native", "platinum", "gold", "silver", "bronze"}
            or any(platform.lower() == "linux" for platform in game.platforms)
        ]
    elif collection == "steam-deck":
        candidates = [
            game for game in candidates
            if (game.proton_tier or "").lower() in {"platinum", "gold", "silver", "native"}
        ]
    page = candidates[:limit]
    return GameListResponse(games=page, total=len(candidates))
