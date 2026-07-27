"""Price/deal backfill shared by game detail endpoints and maintenance jobs."""

import asyncio
import datetime

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session, selectinload

from ..integrations.cheapshark_service import cheapshark_service
from ..integrations.itad_service import itad_service
from ..integrations.rate_limiter import RateLimiter, get_rate_limiter
from ..integrations.steam import extract_steam_app_id, fetch_steam_price
from ..integrations.types import bounded_float
from ..models import Game, PriceSnapshot

PRICE_REFRESH_MAX_AGE = datetime.timedelta(hours=12)

# The SQL gate reads `prices_refreshed_at`, but the authoritative check also
# inspects the snapshots themselves, so a few rows drop out afterwards. Over-fetch
# enough that a full batch still survives the in-Python filter.
_CANDIDATE_POOL_FACTOR = 4
_MIN_CANDIDATE_POOL = 100


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

    limiter = get_rate_limiter()
    rows: list[PriceSnapshot] = []
    steam_row, steam_attempted = await _fetch_steam_snapshot(game, app_id, now, limiter)
    if steam_row:
        rows.append(steam_row)
    itad_row, itad_attempted = await _fetch_itad_snapshot(game, app_id, now, limiter)
    if itad_row:
        rows.append(itad_row)
    cheapshark_rows, cheapshark_attempted = await _fetch_cheapshark_snapshots(
        game,
        app_id,
        now,
        limiter,
        {row.store.lower() for row in rows},
    )
    rows.extend(cheapshark_rows)

    if rows:
        _replace_price_snapshots(db, game, rows)
    attempted = steam_attempted or itad_attempted or cheapshark_attempted
    if not attempted:
        return 0
    game.prices_refreshed_at = now
    db.add(game)
    db.commit()
    return len(rows)


async def _fetch_steam_snapshot(
    game: Game,
    app_id: int | None,
    now: datetime.datetime,
    limiter: RateLimiter,
) -> tuple[PriceSnapshot | None, bool]:
    if app_id is None or not await limiter.acquire("Steam"):
        return None, False
    steam_price = await fetch_steam_price(app_id)
    if not steam_price:
        return None, True
    return PriceSnapshot(
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
    ), True


async def _fetch_itad_snapshot(
    game: Game,
    app_id: int | None,
    now: datetime.datetime,
    limiter: RateLimiter,
) -> tuple[PriceSnapshot | None, bool]:
    if not itad_service.is_configured():
        return None, False
    remaining_before = limiter.remaining("ITAD")
    price_data = await itad_service.fetch_price_data(game.title, steam_appid=app_id)
    attempted = limiter.remaining("ITAD") < remaining_before
    if not price_data:
        return None, attempted
    return PriceSnapshot(
        game_id=game.id,
        source="ITAD",
        store=price_data.store or "Best tracked PC store",
        platform="PC",
        region="DE",
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
        url=price_data.url,
        fetched_at=now,
        created_at=now,
    ), attempted


async def _fetch_cheapshark_snapshots(
    game: Game,
    app_id: int | None,
    now: datetime.datetime,
    limiter: RateLimiter,
    seen_stores: set[str],
) -> tuple[list[PriceSnapshot], bool]:
    remaining_before = limiter.remaining("CheapShark")
    game_id = await cheapshark_service.lookup_game_id(game.title, steam_appid=app_id)
    deals = await cheapshark_service.get_game_deals(game_id) if game_id else []
    if not deals:
        deals = [
            deal for deal in await cheapshark_service.search_deals(game.title, limit=20)
            if _cheapshark_deal_matches_game(deal, game, app_id)
        ]
    attempted = limiter.remaining("CheapShark") < remaining_before
    rows: list[PriceSnapshot] = []
    for deal in sorted(deals, key=_cheapshark_price_sort_key):
        row = _cheapshark_snapshot(game, deal, now)
        if row is None or row.store.lower() in seen_stores:
            continue
        seen_stores.add(row.store.lower())
        rows.append(row)
        if len(seen_stores) >= 12:
            break
    return rows, attempted


def _cheapshark_snapshot(
    game: Game,
    deal: dict,
    now: datetime.datetime,
) -> PriceSnapshot | None:
    normalized = cheapshark_service.normalize_deal(deal)
    if normalized.sale_price is None and normalized.list_price is None:
        return None
    store = str(normalized.raw.get("store_name") or "PC store")
    deal_id = normalized.raw.get("cs_deal_id")
    return PriceSnapshot(
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
    )


def _replace_price_snapshots(
    db: Session,
    game: Game,
    rows: list[PriceSnapshot],
) -> None:
    game.price_snapshots.clear()
    db.flush()
    db.add_all(rows)
    db.flush()
    db.refresh(game, attribute_names=["price_snapshots"])
    from .seo import refresh_game_seo_state
    refresh_game_seo_state(game, content_updated=True)


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
    """
    Highest-ranked games whose prices are stale, best first.

    The freshness gate is in SQL so the sweep advances through the catalog as rows
    get stamped. Filtering a fixed top-N pool in Python instead kept re-offering the
    same few hundred games forever, and nothing below that pool was ever priced.
    """
    cutoff = datetime.datetime.now(datetime.UTC) - PRICE_REFRESH_MAX_AGE
    pool_limit = max(limit * _CANDIDATE_POOL_FACTOR, _MIN_CANDIDATE_POOL)
    games = db.scalars(
        select(Game)
        .where(Game.content_type == "game")
        .where(
            or_(
                Game.prices_refreshed_at.is_(None),
                Game.prices_refreshed_at < cutoff,
            )
        )
        .options(selectinload(Game.price_snapshots))
        .order_by(desc(Game.rank_score), desc(Game.metrix_score))
        .limit(pool_limit)
    ).all()
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
