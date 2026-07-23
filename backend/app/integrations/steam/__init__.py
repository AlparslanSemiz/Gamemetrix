"""Steam Store integration.

  client  — endpoints, timeouts, app-id recovery, shared appdetails fetch
  parsing — release dates, HTML-to-text, requirement/website cleanup
  reviews — review-summary score
  store   — screenshots, requirements, website, price, DLC, release dates
"""

from .client import STEAM_APP_ID_RE, extract_steam_app_id, store_page_url
from .parsing import parse_release_date
from .reviews import get_steam_score
from .store import (
    fetch_steam_dlcs,
    fetch_steam_price,
    fetch_steam_screenshots,
    fetch_steam_system_requirements,
    fetch_steam_website,
    get_steam_release_date,
    get_steam_release_dates,
)

__all__ = [
    "STEAM_APP_ID_RE",
    "extract_steam_app_id",
    "fetch_steam_dlcs",
    "fetch_steam_price",
    "fetch_steam_screenshots",
    "fetch_steam_system_requirements",
    "fetch_steam_website",
    "get_steam_release_date",
    "get_steam_release_dates",
    "get_steam_score",
    "parse_release_date",
    "store_page_url",
]
