"""
Value Score: a separate signal showing how much "value for money" a game offers right now.

Range: 0–100. NEVER feeds into the GameMetrix Score (metrix_score).
Displayed as an independent signal alongside price data.

Formula (weights add to 100):
  Quality component   40 pts  — metrix_score normalised to 0–100
  Deal quality        30 pts  — how close to historical low (or discount size)
  Playtime per dollar 20 pts  — $/hour ratio
  Active-sale bonus   10 pts  — extra reward when a limited sale is live
"""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class PriceData:
    store: str
    currency: str
    list_price: float | None
    sale_price: float | None
    discount_percent: int | None
    historical_low: float | None
    historical_low_date: date | None
    is_free: bool
    is_subscription_included: bool
    subscription_service: str | None
    itad_id: str | None
    fetched_at: datetime
    source: str
    url: str | None = None


def calculate_value_score(
    metrix_score: float,
    price: PriceData,
    playtime_minutes: int,
) -> float | None:
    """
    Return a Value Score in [0, 100], or None when price data is insufficient.

    Pricing, awards, and popularity are excluded from the GameMetrix Score by design.
    This function must never be called as input to calculate_metrix_score().
    """
    # Free or subscription: quality-only scoring with a base bonus
    if price.is_free or price.is_subscription_included:
        return round(min(100.0, metrix_score * 0.4 + 60.0), 1)

    effective_price = price.sale_price if price.sale_price is not None else price.list_price
    if effective_price is None or effective_price <= 0:
        return None

    # ── Quality (40 pts) ─────────────────────────────────────────────────────
    quality = metrix_score * 0.4

    # ── Deal quality (30 pts) ────────────────────────────────────────────────
    if price.historical_low is not None and price.list_price and price.list_price > 0:
        # How close to the all-time low relative to the full list price?
        distance_from_low = effective_price - price.historical_low
        normalised = max(0.0, 1.0 - distance_from_low / price.list_price)
        deal = normalised * 30.0
    elif price.list_price and price.list_price > 0 and price.sale_price is not None:
        cut = (price.list_price - price.sale_price) / price.list_price
        deal = cut * 20.0  # Max 20 pts when historical low is unknown
    else:
        deal = 0.0

    # ── Playtime per dollar (20 pts) ─────────────────────────────────────────
    if playtime_minutes > 0:
        hours = playtime_minutes / 60.0
        dph = effective_price / hours  # dollars per hour
        if dph <= 0.25:
            playtime_pts = 20.0
        elif dph <= 0.50:
            playtime_pts = 18.0
        elif dph <= 1.0:
            playtime_pts = 15.0
        elif dph <= 2.0:
            playtime_pts = 10.0
        elif dph <= 5.0:
            playtime_pts = 5.0
        else:
            playtime_pts = 1.0
    else:
        playtime_pts = 0.0

    # ── Active-sale bonus (10 pts) ───────────────────────────────────────────
    is_on_sale = (
        price.sale_price is not None
        and price.list_price is not None
        and price.sale_price < price.list_price
    )
    sale_bonus = 10.0 if is_on_sale else 0.0

    total = quality + deal + playtime_pts + sale_bonus
    return round(min(100.0, max(0.0, total)), 1)
