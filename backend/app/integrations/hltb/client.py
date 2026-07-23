"""HowLongToBeat search client.

HLTB exposes no stable public API: the site ships a runtime-discovered POST
endpoint plus a short-lived auth token. Both are scraped out of the page's JS
bundle and cached on the client instance, so callers only ever see a match.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .matching import HltbMatch, best_match

log = logging.getLogger(__name__)

BASE_URL = "https://howlongtobeat.com/"
GAME_URL = f"{BASE_URL}game"
IMAGE_URL_PREFIX = f"{BASE_URL}games/"
DEFAULT_SEARCH_PATH = "/api/s"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_HTTP_TIMEOUT = 30
_SEARCH_PAGE_SIZE = 20
_UNAUTHORIZED_STATUSES = {401, 403}

SCRIPT_SRC_RE = re.compile(r"<script[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
POST_ENDPOINT_RE = re.compile(
    r"fetch\s*\(\s*[\"']/api/([a-zA-Z0-9_/]+)[^\"']*[\"']\s*,\s*{[^}]*method:\s*[\"']POST[\"']",
    re.DOTALL | re.IGNORECASE,
)


@dataclass(slots=True)
class _AuthToken:
    token: str | None
    key: str | None
    value: str | None


class HltbClient:
    def __init__(self) -> None:
        self._search_path: str | None = None
        self._auth: _AuthToken | None = None

    async def search(self, title: str, release_year: int | None = None) -> HltbMatch | None:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Referer": BASE_URL},
            follow_redirects=True,
        ) as client:
            return await self._search_with_client(client, title, release_year)

    async def _search_with_client(
        self,
        client: httpx.AsyncClient,
        title: str,
        release_year: int | None,
    ) -> HltbMatch | None:
        search_path = await self._get_search_path(client)
        response = await self._post_search(client, search_path, title)
        if response.status_code in _UNAUTHORIZED_STATUSES:
            # The cached token expired — drop it and retry once with a fresh one.
            self._auth = None
            response = await self._post_search(client, search_path, title)
        if not response.is_success:
            log.debug("HLTB search failed for %r: HTTP %s", title, response.status_code)
            return None

        try:
            rows = response.json().get("data") or []
        except ValueError:
            return None
        return best_match(
            title, release_year, rows, game_url=GAME_URL, image_url_prefix=IMAGE_URL_PREFIX
        )

    async def _post_search(
        self, client: httpx.AsyncClient, search_path: str, title: str
    ) -> httpx.Response:
        auth = await self._get_auth(client, search_path)
        return await client.post(
            f"{BASE_URL}{search_path.lstrip('/')}",
            headers=self._search_headers(auth),
            json=self._search_payload(title, auth),
        )

    async def _get_search_path(self, client: httpx.AsyncClient) -> str:
        if self._search_path:
            return self._search_path

        response = await client.get(BASE_URL)
        response.raise_for_status()
        scripts = SCRIPT_SRC_RE.findall(response.text)
        preferred = [src for src in scripts if "_app-" in src]
        for src in [*preferred, *scripts]:
            script_url = src if src.startswith("http") else f"{BASE_URL}{src.lstrip('/')}"
            script_resp = await client.get(script_url)
            if not script_resp.is_success:
                continue
            match = POST_ENDPOINT_RE.search(script_resp.text)
            if match:
                self._search_path = f"/api/{match.group(1).split('/')[0]}"
                return self._search_path

        self._search_path = DEFAULT_SEARCH_PATH
        return self._search_path

    async def _get_auth(self, client: httpx.AsyncClient, search_path: str) -> _AuthToken:
        if self._auth:
            return self._auth

        response = await client.get(
            f"{BASE_URL}{search_path.lstrip('/')}/init",
            params={"t": int(time.time() * 1000)},
        )
        if not response.is_success:
            self._auth = _AuthToken(token=None, key=None, value=None)
            return self._auth

        data = response.json()
        key = value = None
        for field_name, field_value in data.items():
            lower = field_name.lower()
            if "key" in lower:
                key = str(field_value)
            elif "val" in lower:
                value = str(field_value)
        self._auth = _AuthToken(token=str(data.get("token") or ""), key=key, value=value)
        return self._auth

    def _search_headers(self, auth: _AuthToken) -> dict[str, str]:
        headers = {
            "content-type": "application/json",
            "accept": "*/*",
            "User-Agent": USER_AGENT,
            "Referer": BASE_URL,
            "Origin": BASE_URL.rstrip("/"),
        }
        if auth.token:
            headers["x-auth-token"] = auth.token
        if auth.key:
            headers["x-hp-key"] = auth.key
        if auth.value:
            headers["x-hp-val"] = auth.value
        return headers

    def _search_payload(self, title: str, auth: _AuthToken) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "searchType": "games",
            "searchTerms": title.split(),
            "searchPage": 1,
            "size": _SEARCH_PAGE_SIZE,
            "searchOptions": {
                "games": {
                    "userId": 0,
                    "platform": "",
                    "sortCategory": "popular",
                    "rangeCategory": "main",
                    "rangeTime": {"min": 0, "max": 0},
                    "gameplay": {"perspective": "", "flow": "", "genre": "", "difficulty": ""},
                    "rangeYear": {"max": "", "min": ""},
                    "modifier": "hide_dlc",
                },
                "users": {"sortCategory": "postcount"},
                "lists": {"sortCategory": "follows"},
                "filter": "",
                "sort": 0,
                "randomizer": 0,
            },
            "useCache": True,
        }
        if auth.key:
            payload[auth.key] = auth.value
        return payload
