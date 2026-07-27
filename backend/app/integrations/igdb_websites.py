"""IGDB website-field helpers shared by catalog import and metadata refresh."""

from __future__ import annotations

from urllib.parse import urlsplit


def extract_official_website(raw: dict) -> str | None:
    """Return IGDB's category/type 1 official website, never a store/profile URL."""
    for item in raw.get("websites") or []:
        if not isinstance(item, dict):
            continue
        website_type = item.get("type", item.get("category"))
        url = item.get("url")
        if website_type != 1 or not isinstance(url, str):
            continue
        candidate = url.strip()
        parsed = urlsplit(candidate)
        if (
            len(candidate) <= 500
            and parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
        ):
            return candidate
    return None
