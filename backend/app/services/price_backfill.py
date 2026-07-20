"""Price/deal backfill shared by game detail endpoints and maintenance jobs."""

import asyncio
import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from ..integrations.cheapshark_service import cheapshark_service
from ..integrations.itad_service import itad_service
from ..integrations.rate_limiter import get_rate_limiter
from ..integrations.steam import extract_steam_app_id, fetch_steam_price
from ..integrations.types import bounded_float
from ..models import Game, PriceSnapshot

PRICE_REFRESH_MAX_AGE = datetime.timedelta(hours=12)


def _cheapshark_price_sort_key(deal: dict) -> float:
    amount = bounded_float(deal.get("salePrice"), maximum=1_000_000.0)
    return amount if amount is not None else float("inf")


def _snapshot_is_recent(snapshot: PriceSnapshot, now: datetime.datetime | None = None) -> bool:
    now = now or datetime.datetime.now(datetime.UTC)
    fetched_at = snapshot.fetched_at
    if fetched_at is None:
        return False
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=datetime.UTC)
    return fetched_at >= now - PRICE_REFRESH_MAX_AGE


def _snapshot_needs_repair(snapshot: PriceSnapshot, app_id: int | None) -> bool:
    raw = snapshot.raw_payload or {}
    if snapshot.store.startswith("Store "):
        return True
    if snapshot.source == "CheapShark" and app_id is not None:
        steam_app_id = raw.get("steam_app_id")
        if steam_app_id is None:
            return True
        return str(steam_app_id) != str(app_id)
    return False


def price_snapshots_need_refresh(game: Game) -> bool:
    snapshots = game.price_snapshots or []
    if not snapshots:
        if game.prices_refreshed_at is not None:
            refreshed_at = game.prices_refreshed_at
            if refreshed_at.tzinfo is None:
                refreshed_at = refreshed_at.replace(tzinfo=datetime.UTC)
            if refreshed_at >= datetime.datetime.now(datetime.UTC) - PRICE_REFRESH_MAX_AGE:
                return False
        return True
    app_id = extract_steam_app_id(game.cover_url, game.image_url, game.slug)
    has_price = any(
        snapshot.is_free
        or snapshot.sale_price is not None
        or snapshot.list_price is not None
        for snapshot in snapshots
    )
    if not has_price:
        return True
    if any(_snapshot_needs_repair(snapshot, app_id) for snapshot in snapshots):
        return True
    return not any(_snapshot_is_recent(snapshot) for snapshot in snapshots)


async def fetch_and_store_prices(
    db: Session,
    game: Game,
) -> int:
    now = datetime.datetime.now(datetime.UTC)
    app_id = extract_steam_app_id(game.cover_url, game.image_url, game.slug)

    if not price_snapshots_need_refresh(game):
        return 0

    rows: list[PriceSnapshot] = []
    limiter = get_rate_limiter()
    attempted = False

    if app_id is not None and await limiter.acquire("Steam"):
        attempted = True
        steam_price = await fetch_steam_price(app_id)
        if steam_price:
            rows.append(PriceSnapshot(
                game_id=game.id,
                source="Steam",
                external_price_id=str(app_id),
                store="Steam",
                platform="PC",
                region="US",
                currency=steam_price["currency"],
                list_price=steam_price["list_price"],
                sale_price=steam_price["sale_price"],
                discount_percent=steam_price["discount_percent"],
                is_free=steam_price["is_free"],
                url=steam_price["url"],
                raw_payload=steam_price["raw"],
                fetched_at=now,
                created_at=now,
            ))

    if itad_service.is_configured():
        remaining_before = limiter.remaining("ITAD")
        price_data = await itad_service.fetch_price_data(game.title, steam_appid=app_id)
        attempted = attempted or limiter.remaining("ITAD") < remaining_before
        if price_data:
            rows.append(PriceSnapshot(
                game_id=game.id,
                source="ITAD",
                store=price_data.store or "Best tracked PC store",
                platform="PC",
                region="EU",
                currency=price_data.currency,
                list_price=price_data.list_price,
                sale_price=price_data.sale_price,
                discount_percent=price_data.discount_percent,
                historical_low=price_data.historical_low,
                historical_low_date=price_data.historical_low_date,
                is_free=price_data.is_free,
                is_subscription_included=price_data.is_subscription_included,
                subscription_service=price_data.subscription_service,
                itad_id=price_data.itad_id,
                fetched_at=now,
                created_at=now,
            ))

    cheapshark_before = limiter.remaining("CheapShark")
    deals = []
    cs_game_id = await cheapshark_service.lookup_game_id(game.title, steam_appid=app_id)
    if cs_game_id:
        deals = await cheapshark_service.get_game_deals(cs_game_id)
    if not deals:
        deals = [
            deal for deal in await cheapshark_service.search_deals(game.title, limit=20)
            if _cheapshark_deal_matches_game(deal, game, app_id)
        ]
    attempted = attempted or limiter.remaining("CheapShark") < cheapshark_before
    if deals:
        seen_stores: set[str] = {row.store.lower() for row in rows}
        sorted_deals = sorted(deals, key=_cheapshark_price_sort_key)
        for deal in sorted_deals:
            normalized = cheapshark_service.normalize_deal(deal)
            if normalized.sale_price is None and normalized.list_price is None:
                continue
            store = str(normalized.raw.get("store_name") or "PC store")
            store_key = store.lower()
            if store_key in seen_stores:
                continue
            seen_stores.add(store_key)
            deal_id = normalized.raw.get("cs_deal_id")
            rows.append(PriceSnapshot(
                game_id=game.id,
                source="CheapShark",
                external_price_id=str(deal_id) if deal_id else None,
                store=store,
                platform="PC",
                region="US",
                currency=normalized.currency,
                list_price=normalized.list_price,
                sale_price=normalized.sale_price,
                discount_percent=int(normalized.raw.get("savings_pct", 0) or 0),
                url=f"https://www.cheapshark.com/redirect?dealID={deal_id}" if deal_id else None,
                raw_payload=normalized.raw,
                fetched_at=now,
                created_at=now,
            ))
            if len(seen_stores) >= 12:
                break

    if rows:
        game.price_snapshots.clear()
        db.flush()
        db.add_all(rows)
        db.flush()
        db.refresh(game, attribute_names=["price_snapshots"])
        from .seo import refresh_game_seo_state
        refresh_game_seo_state(game, content_updated=True)
    if not attempted:
        return 0
    game.prices_refreshed_at = now
    db.add(game)
    db.commit()
    return len(rows)


_PRICE_ADDON_TERMS = (
    "upgrade",
    "dlc",
    "soundtrack",
    "bundle",
    "pack",
    "season pass",
    "expansion",
)


def _price_title_key(value: str) -> str:
    return " ".join(
        "".join(ch.lower() if ch.isalnum() else " " for ch in value).split()
    )


def _cheapshark_deal_matches_game(raw: dict, game: Game, app_id: int | None) -> bool:
    title = str(raw.get("title") or "")
    normalized_title = _price_title_key(title)
    expected = _price_title_key(game.title)
    if not normalized_title:
        return False
    if app_id is not None and raw.get("steamAppID") and str(raw.get("steamAppID")) != str(app_id):
        return False
    if any(term in normalized_title for term in _PRICE_ADDON_TERMS) and normalized_title != expected:
        return False
    return normalized_title == expected or expected in normalized_title or normalized_title in expected


def price_backfill_candidates(db: Session, limit: int) -> list[Game]:
    pool_limit = max(limit * 8, 200)
    games = list(
        db.scalars(
            select(Game)
            .where(Game.content_type == "game")
            .options(selectinload(Game.price_snapshots))
            .order_by(desc(Game.rank_score), desc(Game.metrix_score))
            .limit(pool_limit)
        ).all()
    )
    due = [game for game in games if price_snapshots_need_refresh(game)]
    return due[:limit]


async def price_backfill_batch(
    limit: int = 48,
    *,
    inter_game_delay: float = 0.35,
    refresh_seo: bool = True,
) -> dict[str, int]:
    from ..database import SessionLocal

    considered = stored = skipped = failed = 0
    with SessionLocal() as db:
        candidates = [game.id for game in price_backfill_candidates(db, limit)]

    for game_id in candidates:
        considered += 1
        if inter_game_delay > 0:
            await asyncio.sleep(inter_game_delay)
        with SessionLocal() as db:
            game = db.get(Game, game_id)
            if game is None:
                skipped += 1
                continue
            try:
                rows = await fetch_and_store_prices(db, game)
            except Exception:
                failed += 1
                continue
            if rows:
                stored += rows
            else:
                skipped += 1
    if stored and refresh_seo:
        with SessionLocal() as db:
            from .seo import refresh_catalog_seo_states
            refresh_catalog_seo_states(db)
            db.commit()
    return {
        "considered": considered,
        "stored": stored,
        "skipped": skipped,
        "failed": failed,
    }
