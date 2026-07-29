from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy import cast, desc, exists, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..config import get_settings
from ..models import Game, PriceSnapshot
from ..schemas import CatalogGameListResponse, CatalogGameRead
from ..services.catalog_projection import catalog_load_options
from ..services.seo import (
    CANONICAL_ORIGIN,
    MIN_GENRE_LANDING_GAMES,
    SITEMAP_CHUNK_SIZE,
    SitemapEntry,
    game_url_sitemap,
    genre_slug,
    indexable_genre_facets,
    sitemap_chunk_count,
    sitemap_index_document,
    static_url_sitemap,
)


router = APIRouter(tags=["seo"])
CuratedCollection = Literal["home", "linux", "steam-deck", "free", "deals", "year", "genre"]

# Sitemaps are pure derived data — a one-hour edge cache with a day of
# stale-while-revalidate keeps crawlers fast without hammering the catalog.
_SITEMAP_CACHE = "public, max-age=3600, stale-while-revalidate=86400"
_FRESH_PRICE_WINDOW = timedelta(hours=24)
# A curated landing page (Linux, Steam Deck, free, deals, a given year) is only
# advertised once it has enough qualifying games to be worth crawling.
_MIN_CURATED_GAMES = 5


def _indexable_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Game).where(Game.seo_indexable.is_(True))) or 0


def _latest_indexable_update(db: Session) -> datetime | None:
    return db.scalar(select(func.max(Game.seo_updated_at)).where(Game.seo_indexable.is_(True)))


def _fresh_prices(game: Game, fresh_before: datetime) -> list[PriceSnapshot]:
    return [
        price for price in game.price_snapshots
        if price.fetched_at.replace(tzinfo=price.fetched_at.tzinfo or UTC) >= fresh_before
    ]


def _curated_paths(db: Session, games: list[Game], fresh_before: datetime) -> list[str]:
    linux_count = sum(
        1 for game in games
        if (game.proton_tier or "").lower() in {"native", "platinum", "gold", "silver", "bronze"}
        or any(platform.lower() == "linux" for platform in game.platforms)
    )
    deck_count = sum(
        1 for game in games
        if (game.proton_tier or "").lower() in {"native", "platinum", "gold", "silver"}
    )
    free_count = sum(1 for game in games if any(price.is_free for price in _fresh_prices(game, fresh_before)))
    deal_count = sum(
        1 for game in games
        if any(price.is_free or (price.discount_percent or 0) >= 40 for price in _fresh_prices(game, fresh_before))
    )
    paths: list[str] = []
    if linux_count >= _MIN_CURATED_GAMES:
        paths.append("/best/linux-games")
    if deck_count >= _MIN_CURATED_GAMES:
        paths.append("/best/steam-deck-games")
    if free_count >= _MIN_CURATED_GAMES:
        paths.append("/best/free-pc-games")
    if deal_count >= _MIN_CURATED_GAMES:
        paths.append("/deals")
    paths.extend(f"/best/{slug}-games" for slug, _, _ in indexable_genre_facets(db, MIN_GENRE_LANDING_GAMES))
    return paths


def _curated_years(games: list[Game]) -> list[int]:
    counts: dict[int, int] = {}
    for game in games:
        counts[game.release_year] = counts.get(game.release_year, 0) + 1
    return sorted((year for year, count in counts.items() if count >= _MIN_CURATED_GAMES), reverse=True)


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap_index(db: Session = Depends(get_db)) -> Response:
    """The sitemap index Google reads first: one static child plus N game chunks."""
    latest = _latest_indexable_update(db)
    chunks = sitemap_chunk_count(_indexable_count(db))
    children: list[tuple[str, datetime | None]] = [(f"{CANONICAL_ORIGIN}/sitemap-static.xml", latest)]
    children.extend(
        (f"{CANONICAL_ORIGIN}/sitemap-games-{index}.xml", latest)
        for index in range(1, chunks + 1)
    )
    return Response(
        sitemap_index_document(children),
        media_type="application/xml",
        headers={"Cache-Control": _SITEMAP_CACHE},
    )


@router.get("/sitemap-games-{chunk}.xml", include_in_schema=False)
def sitemap_games(chunk: int = Path(ge=1), db: Session = Depends(get_db)) -> Response:
    """One 10k-URL slice of the published game cohort, ordered deterministically."""
    published = min(_indexable_count(db), get_settings().SEO_INDEX_LIMIT)
    offset = (chunk - 1) * SITEMAP_CHUNK_SIZE
    page_size = min(SITEMAP_CHUNK_SIZE, published - offset)
    if page_size <= 0:
        raise HTTPException(status_code=404, detail="No such sitemap chunk")
    games = list(
        db.scalars(
            select(Game)
            .where(Game.seo_indexable.is_(True))
            .order_by(desc(Game.rank_score), Game.slug)
            .offset(offset)
            .limit(page_size)
        ).all()
    )
    return Response(
        game_url_sitemap(games),
        media_type="application/xml",
        headers={"Cache-Control": _SITEMAP_CACHE},
    )


@router.get("/sitemap-static.xml", include_in_schema=False)
def sitemap_static(db: Session = Depends(get_db)) -> Response:
    """Landing, curation, genre and year pages — the non-game half of the index."""
    games = list(
        db.scalars(
            select(Game)
            .where(Game.seo_indexable.is_(True))
            .options(selectinload(Game.price_snapshots))
            .order_by(desc(Game.rank_score), Game.slug)
            .limit(get_settings().SEO_INDEX_LIMIT)
        ).all()
    )
    fresh_before = datetime.now(UTC) - _FRESH_PRICE_WINDOW
    entries = [
        SitemapEntry(f"{CANONICAL_ORIGIN}/", "daily", "1.0"),
        SitemapEntry(f"{CANONICAL_ORIGIN}/about", "monthly", "0.3"),
    ]
    entries.extend(
        SitemapEntry(f"{CANONICAL_ORIGIN}{path}", "weekly", "0.7")
        for path in _curated_paths(db, games, fresh_before)
    )
    entries.extend(
        SitemapEntry(f"{CANONICAL_ORIGIN}/best/games/{year}", "weekly", "0.6")
        for year in _curated_years(games)
    )
    lastmod = max((game.seo_updated_at for game in games if game.seo_updated_at), default=None)
    return Response(
        static_url_sitemap(entries, lastmod),
        media_type="application/xml",
        headers={"Cache-Control": _SITEMAP_CACHE},
    )


@router.get("/api/seo/genres")
def seo_genres(db: Session = Depends(get_db)) -> dict:
    """Genres that currently qualify for a landing page, newest counts first."""
    return {
        "genres": [
            {"slug": slug, "name": name, "count": count}
            for slug, name, count in indexable_genre_facets(db, MIN_GENRE_LANDING_GAMES)
        ],
    }


@router.get("/api/seo/curated/{collection}", response_model=CatalogGameListResponse)
def curated_games(
    collection: CuratedCollection,
    year: int | None = Query(default=None, ge=1970, le=2100),
    genre: str | None = Query(default=None, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    limit: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
) -> CatalogGameListResponse:
    fresh_before = datetime.now(UTC) - _FRESH_PRICE_WINDOW
    conditions = [Game.seo_indexable.is_(True)]
    if collection == "year":
        if year is None:
            raise HTTPException(status_code=422, detail="year is required")
        conditions.append(Game.release_year == year)
    elif collection == "free":
        conditions.append(
            exists(
                select(PriceSnapshot.id).where(
                    PriceSnapshot.game_id == Game.id,
                    PriceSnapshot.is_free.is_(True),
                    PriceSnapshot.fetched_at >= fresh_before,
                )
            )
        )
    elif collection == "deals":
        conditions.append(
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
        facets = {slug: display for slug, display, _ in indexable_genre_facets(db, MIN_GENRE_LANDING_GAMES)}
        display_name = facets.get(genre)
        if display_name is None:
            raise HTTPException(status_code=404, detail="Unknown genre")
        conditions.append(cast(Game.genres, JSONB).contains([display_name]))
    elif collection == "linux":
        conditions.append(or_(
            Game.proton_tier.in_({"native", "platinum", "gold", "silver", "bronze"}),
            cast(Game.platforms, JSONB).contains(["Linux"]),
        ))
    elif collection == "steam-deck":
        conditions.append(
            Game.proton_tier.in_({"platinum", "gold", "silver", "native"})
        )

    total = min(
        db.scalar(select(func.count()).select_from(Game).where(*conditions)) or 0,
        400,
    )
    page = list(
        db.scalars(
            select(Game)
            .where(*conditions)
            .options(*catalog_load_options(include_prices=True))
            .order_by(desc(Game.rank_score), desc(Game.metrix_score), Game.title)
            .limit(min(limit, total))
        ).all()
    )
    return CatalogGameListResponse(
        games=[CatalogGameRead.model_validate(game) for game in page],
        total=total,
    )
