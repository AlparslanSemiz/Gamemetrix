"""Backward-compatible ITAD function facade.

The class-based adapter in :mod:`itad_service` owns authentication, persistent
budgets, and the current upstream endpoint contract. Keep these functions for
older callers without maintaining a second, divergent HTTP implementation.
"""

from .itad_service import DEFAULT_ITAD_COUNTRY, itad_service
from .value_score import PriceData, calculate_value_score  # noqa: F401


async def lookup_itad_id(title: str) -> str | None:
    return await itad_service.lookup_id(title)


async def get_current_prices(
    itad_id: str,
    country: str = DEFAULT_ITAD_COUNTRY,
) -> list[dict]:
    return await itad_service.get_prices(itad_id, country)


async def get_historical_low(
    itad_id: str,
    country: str = DEFAULT_ITAD_COUNTRY,
) -> dict | None:
    return await itad_service.get_history_low(itad_id, country)


async def get_subscription_info(itad_id: str) -> list[str]:
    return await itad_service.get_subscriptions(itad_id)


async def fetch_price_data(
    title: str,
    country: str = DEFAULT_ITAD_COUNTRY,
) -> PriceData | None:
    return await itad_service.fetch_price_data(title, country)
