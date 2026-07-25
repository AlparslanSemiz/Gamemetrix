"""Exact-identity metadata enrichment through the Wikidata Query Service."""

from __future__ import annotations

import re
from datetime import date

import httpx

from ..config import USER_AGENT
from .rate_limiter import get_rate_limiter
from .types import NormalizedGame


WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
_QID_RE = re.compile(r"/(Q\d+)$")


def _binding_value(row: dict, key: str) -> str | None:
    value = row.get(key)
    if not isinstance(value, dict):
        return None
    raw = value.get("value")
    return str(raw).strip() if raw is not None and str(raw).strip() else None


def _append_unique(values: list[str], value: str | None) -> None:
    if value and value not in values:
        values.append(value)


def _platform(value: str) -> str:
    lowered = value.casefold()
    if "windows" in lowered:
        return "PC"
    if lowered == "macos" or "mac os" in lowered:
        return "macOS"
    if "playstation" in lowered:
        match = re.search(r"(\d+)", value)
        return f"PlayStation {match.group(1)}" if match else "PlayStation"
    if "xbox" in lowered:
        return value.replace("Xbox series", "Xbox Series")
    return value


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _sparql_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


class WikidataService:
    def is_configured(self) -> bool:
        return True

    def build_exact_query(
        self,
        *,
        steam_app_id: int | None = None,
        igdb_slug: str | None = None,
    ) -> str | None:
        identity_filters: list[str] = []
        if steam_app_id and steam_app_id > 0:
            identity_filters.append(f'?item wdt:P1733 "{int(steam_app_id)}".')
        if igdb_slug and igdb_slug.strip():
            identity_filters.append(f'?item wdt:P5794 "{_sparql_literal(igdb_slug.strip())}".')
        if not identity_filters:
            return None
        identity = "\n  ".join(identity_filters)
        return f"""
SELECT ?item ?itemLabel ?releaseDate ?developerLabel ?publisherLabel
       ?genreLabel ?platformLabel ?website ?steamId ?igdbSlug WHERE {{
  {identity}
  OPTIONAL {{ ?item wdt:P577 ?releaseDate. }}
  OPTIONAL {{ ?item wdt:P178 ?developer. }}
  OPTIONAL {{ ?item wdt:P123 ?publisher. }}
  OPTIONAL {{ ?item wdt:P136 ?genre. }}
  OPTIONAL {{ ?item wdt:P400 ?platform. }}
  OPTIONAL {{ ?item wdt:P856 ?website. }}
  OPTIONAL {{ ?item wdt:P1733 ?steamId. }}
  OPTIONAL {{ ?item wdt:P5794 ?igdbSlug. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 250
""".strip()

    async def lookup_exact(
        self,
        *,
        steam_app_id: int | None = None,
        igdb_slug: str | None = None,
    ) -> NormalizedGame | None:
        query = self.build_exact_query(steam_app_id=steam_app_id, igdb_slug=igdb_slug)
        if query is None or not await get_rate_limiter().acquire("Wikidata"):
            return None
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                WIKIDATA_SPARQL_URL,
                params={"query": query, "format": "json"},
                headers={
                    "User-Agent": f"{USER_AGENT} (https://gamemetrix.me)",
                    "Accept": "application/sparql-results+json",
                },
            )
            response.raise_for_status()
        payload = response.json()
        results = payload.get("results") if isinstance(payload, dict) else {}
        bindings = results.get("bindings") if isinstance(results, dict) else []
        return self.normalize_bindings(bindings if isinstance(bindings, list) else [])

    def normalize_bindings(self, bindings: list[dict]) -> NormalizedGame | None:
        rows = [row for row in bindings if isinstance(row, dict)]
        if not rows:
            return None
        first = rows[0]
        item_url = _binding_value(first, "item")
        match = _QID_RE.search(item_url or "")
        if not match:
            return None
        qid = match.group(1)
        name = _binding_value(first, "itemLabel")
        if not name:
            return None

        genres: list[str] = []
        platforms: list[str] = []
        releases: list[date] = []
        developer = publisher = website = steam_id = igdb_slug = None
        for row in rows:
            genre = _binding_value(row, "genreLabel")
            platform = _binding_value(row, "platformLabel")
            _append_unique(genres, genre)
            if platform:
                _append_unique(platforms, _platform(platform))
            released = _date(_binding_value(row, "releaseDate"))
            if released and released not in releases:
                releases.append(released)
            developer = developer or _binding_value(row, "developerLabel")
            publisher = publisher or _binding_value(row, "publisherLabel")
            website = website or _binding_value(row, "website")
            steam_id = steam_id or _binding_value(row, "steamId")
            igdb_slug = igdb_slug or _binding_value(row, "igdbSlug")

        raw: dict[str, object] = {"qid": qid}
        if website:
            raw["website"] = website
        if steam_id and steam_id.isdigit():
            raw["steam_app_id"] = int(steam_id)
        if igdb_slug:
            raw["igdb_slug"] = igdb_slug
        return NormalizedGame(
            source="Wikidata",
            external_id=qid,
            name=name,
            external_url=f"https://www.wikidata.org/wiki/{qid}",
            release_date=min(releases) if releases else None,
            platforms=platforms,
            genres=genres,
            developer=developer,
            publisher=publisher,
            raw=raw,
        )


wikidata_service = WikidataService()
