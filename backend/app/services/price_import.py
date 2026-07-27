"""Admin single-game price fetches: pull one source's price and snapshot it.

Distinct from `price_backfill.py`, which sweeps the whole catalog. Here an
operator asks for one game's price on demand from the admin surface.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..integrations.cheapshark_service import cheapshark_service
from ..integrations.itad_service import itad_service
from ..integrations.title_matching import titles_match
from ..models import Game, PriceSnapshot

_CHEAPSHARK_DEAL_LIMIT = 5


async def import_itad_price(db: Session, game: Game, country: str) -> dict[str, object]:
    price_data = await itad_service.fetch_price_data(game.title, country=country)
    if not price_data:
        return {"stored": False, "reason": "No ITAD price data found"}

    now = datetime.now(UTC)
    db.add(
        PriceSnapshot(
            game_id=game.id,
            source="ITAD",
            store=price_data.store,
            region=country,
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
        )
    )
    db.commit()
    return {
        "stored": True,
        "store": price_data.store,
        "list_price": price_data.list_price,
        "sale_price": price_data.sale_price,
        "currency": price_data.currency,
        "historical_low": price_data.historical_low,
        "is_free": price_data.is_free,
        "subscription": price_data.subscription_service,
    }


async def import_cheapshark_price(db: Session, game: Game) -> dict[str, object]:
    deals = await cheapshark_service.search_deals(game.title, limit=_CHEAPSHARK_DEAL_LIMIT)
    if not deals:
        return {"stored": False, "reason": "No CheapShark deals found"}

    cheapest = _cheapest_matching_deal(game, deals)
    if cheapest is None:
        return {"stored": False, "reason": "No matching valid deal found"}

    now = datetime.now(UTC)
    db.add(
        PriceSnapshot(
            game_id=game.id,
            source="CheapShark",
            store=cheapest.raw.get("store_name", ""),
            region="US",
            currency="USD",
            list_price=cheapest.list_price,
            sale_price=cheapest.sale_price,
            discount_percent=int(cheapest.raw.get("savings_pct", 0)),
            raw_payload=cheapest.raw,
            fetched_at=now,
            created_at=now,
        )
    )
    db.commit()
    return {
        "stored": True,
        "store": cheapest.raw.get("store_name"),
        "list_price": cheapest.list_price,
        "sale_price": cheapest.sale_price,
        "currency": "USD",
    }


def _cheapest_matching_deal(game: Game, deals: list):
    normalized = [
        deal
        for deal in (cheapshark_service.normalize_deal(raw) for raw in deals)
        if titles_match(game.title, deal.name)
        and (deal.sale_price is not None or deal.list_price is not None)
    ]
    if not normalized:
        return None
    return min(normalized, key=_deal_price)


def _deal_price(deal) -> float:
    if deal.sale_price is not None:
        return deal.sale_price
    return deal.list_price if deal.list_price is not None else float("inf")
