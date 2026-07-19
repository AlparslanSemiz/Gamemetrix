"""
HowLongToBeat playtime enrichment.

HowLongToBeat does not expose a stable public API. The website currently uses a
runtime-discovered POST endpoint plus a short-lived auth token; this adapter keeps
that logic contained so the rest of the app only sees normalized minutes.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

import httpx
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ..models import Game


log = logging.getLogger(__name__)

BASE_URL = "https://howlongtobeat.com/"
GAME_URL = f"{BASE_URL}game"
IMAGE_URL_PREFIX = f"{BASE_URL}games/"
DEFAULT_SEARCH_PATH = "/api/s"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MIN_MATCH_SIMILARITY = 0.72

SCRIPT_SRC_RE = re.compile(r"<script[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
POST_ENDPOINT_RE = re.compile(
    r"fetch\s*\(\s*[\"']/api/([a-zA-Z0-9_/]+)[^\"']*[\"']\s*,\s*{[^}]*method:\s*[\"']POST[\"']",
    re.DOTALL | re.IGNORECASE,
)

KNOWN_COVER_URLS: dict[str, str] = {
    "the-witcher-goodies-collection-709179": "https://images.gog-statics.com/a344e6ee3a17af9e6529dd22deda462aa0c5cc7a856d3a4f8cb84e15d31a3a76.jpg",
    "rock-band-music-store-28624": "https://cdn2.steamgriddb.com/grid/a1d2282208205a6832a37601df840de2.png",
    "ea-play-hub-481920": "https://image.api.playstation.com/gs2-sec/appkgo/prod/CUSA16175_00/2/i_06a73a7513560fbfe586ab17d2a66df2c1bfec61431138c6cc60a07841dd6d2b/i/pic0.png?thumb=true&w=512",
    "last-fm-28854": "https://upload.wikimedia.org/wikipedia/commons/c/c4/Lastfm_logo.svg",
    "into-the-war-20690": "https://howlongtobeat.com/games/Into_The_War_header.jpg",
}


@dataclass(slots=True)
class HltbMatch:
    hltb_id: int
    title: str
    url: str
    image_url: str | None
    similarity: float
    release_year: int | None
    main_story_minutes: int
    main_extra_minutes: int
    completionist_minutes: int
    all_styles_minutes: int
    raw: dict[str, Any]


@dataclass(slots=True)
class _AuthToken:
    token: str | None
    key: str | None
    value: str | None


def _normalize_title(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _similarity(expected: str, candidate: str | None) -> float:
    expected_norm = _normalize_title(expected)
    candidate_norm = _normalize_title(candidate)
    if not expected_norm or not candidate_norm:
        return 0.0
    score = SequenceMatcher(None, expected_norm, candidate_norm).ratio()
    expected_numbers = {part for part in expected_norm.split() if part.isdigit()}
    candidate_numbers = {part for part in candidate_norm.split() if part.isdigit()}
    if expected_numbers and not expected_numbers <= candidate_numbers:
        score -= 0.1
    return max(0.0, score)


def _seconds_to_minutes(value: Any) -> int:
    try:
        seconds = int(value or 0)
    except (TypeError, ValueError):
        return 0
    if seconds <= 0:
        return 0
    return max(1, round(seconds / 60))


def _is_missing_cover(value: str | None) -> bool:
    return not value or value.strip().lower() in {"", "none", "null"}


def _igdb_cover_from_source_scores(game: Game) -> str | None:
    for score in game.source_scores or []:
        raw_response = score.get("response")
        if not isinstance(raw_response, dict):
            continue
        cover = raw_response.get("cover")
        if not isinstance(cover, dict):
            continue
        url = cover.get("url")
        if not isinstance(url, str) or not url:
            continue
        normalized = url.replace("//", "https://", 1)
        return normalized.replace("t_thumb", "t_cover_big_2x")
    return None


def _best_playtime_minutes(match: HltbMatch) -> int:
    return (
        match.main_story_minutes
        or match.all_styles_minutes
        or match.main_extra_minutes
        or match.completionist_minutes
        or 0
    )


class HltbClient:
    def __init__(self) -> None:
        self._search_path: str | None = None
        self._auth: _AuthToken | None = None

    async def search(self, title: str, release_year: int | None = None) -> HltbMatch | None:
        async with httpx.AsyncClient(
            timeout=30,
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
        auth = await self._get_auth(client, search_path)
        payload = self._search_payload(title, auth)
        response = await client.post(
            f"{BASE_URL}{search_path.lstrip('/')}",
            headers=self._search_headers(auth),
            json=payload,
        )
        if response.status_code in {401, 403}:
            self._auth = None
            auth = await self._get_auth(client, search_path)
            response = await client.post(
                f"{BASE_URL}{search_path.lstrip('/')}",
                headers=self._search_headers(auth),
                json=self._search_payload(title, auth),
            )
        if not response.is_success:
            log.debug("HLTB search failed for %r: HTTP %s", title, response.status_code)
            return None
        try:
            data = response.json().get("data") or []
        except ValueError:
            return None
        return self._best_match(title, release_year, data)

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
            if not match:
                continue
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
            "size": 20,
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

    def _best_match(
        self,
        title: str,
        release_year: int | None,
        rows: list[dict[str, Any]],
    ) -> HltbMatch | None:
        matches: list[tuple[float, HltbMatch]] = []
        for row in rows:
            game_type = str(row.get("game_type") or "game").lower()
            if game_type not in {"game", ""}:
                continue
            similarity = max(
                _similarity(title, row.get("game_name")),
                _similarity(title, row.get("game_alias")),
            )
            hltb_id = row.get("game_id")
            if not hltb_id:
                continue
            image = row.get("game_image")
            release = row.get("release_world")
            try:
                row_year = int(release) if release else None
            except (TypeError, ValueError):
                row_year = None
            image_url = f"{IMAGE_URL_PREFIX}{image}" if isinstance(image, str) and image else None
            match = HltbMatch(
                hltb_id=int(hltb_id),
                title=str(row.get("game_name") or title),
                url=f"{GAME_URL}/{hltb_id}",
                image_url=image_url,
                similarity=round(similarity, 3),
                release_year=row_year,
                main_story_minutes=_seconds_to_minutes(row.get("comp_main")),
                main_extra_minutes=_seconds_to_minutes(row.get("comp_plus")),
                completionist_minutes=_seconds_to_minutes(row.get("comp_100")),
                all_styles_minutes=_seconds_to_minutes(row.get("comp_all")),
                raw=row,
            )
            if match.similarity < MIN_MATCH_SIMILARITY:
                continue
            rank = match.similarity
            if release_year and row_year and abs(release_year - row_year) <= 1:
                rank += 0.06
            if _best_playtime_minutes(match) > 0:
                rank += 0.03
            matches.append((rank, match))
        if not matches:
            return None
        return max(matches, key=lambda item: item[0])[1]


def apply_hltb_match(game: Game, match: HltbMatch, refresh_existing: bool = False) -> bool:
    changed = False
    now = datetime.now(UTC)
    fields = {
        "hltb_id": match.hltb_id,
        "hltb_url": match.url,
        "hltb_main_story_minutes": match.main_story_minutes,
        "hltb_main_extra_minutes": match.main_extra_minutes,
        "hltb_completionist_minutes": match.completionist_minutes,
        "hltb_all_styles_minutes": match.all_styles_minutes,
    }
    for field, value in fields.items():
        if getattr(game, field) != value:
            setattr(game, field, value)
            changed = True

    primary_minutes = _best_playtime_minutes(match)
    if primary_minutes > 0 and (refresh_existing or (game.playtime_minutes or 0) <= 0):
        game.playtime_minutes = primary_minutes
        changed = True

    if repair_missing_cover(game, match.image_url):
        changed = True

    if game.hltb_refreshed_at != now:
        game.hltb_refreshed_at = now
        changed = True
    return changed


def repair_missing_cover(game: Game, hltb_image_url: str | None = None) -> bool:
    if not _is_missing_cover(game.cover_url):
        return False
    cover_url = (
        KNOWN_COVER_URLS.get(game.slug)
        or hltb_image_url
        or _igdb_cover_from_source_scores(game)
    )
    if not cover_url:
        return False
    game.cover_url = cover_url[:500]
    game.image_url = cover_url[:500]
    return True


async def backfill_hltb_playtimes(
    db: Session,
    target: int = 200,
    refresh_existing: bool = False,
    delay_seconds: float = 0.2,
) -> dict[str, int]:
    cover_missing = or_(
        Game.cover_url.is_(None),
        func.trim(Game.cover_url) == "",
        func.lower(Game.cover_url).in_(("none", "null")),
    )
    query = select(Game).where(Game.content_type == "game")
    if refresh_existing:
        query = query.where(or_(Game.hltb_id.is_not(None), Game.playtime_minutes > 0, cover_missing))
    else:
        query = query.where(or_(Game.hltb_id.is_(None), Game.playtime_minutes <= 0, cover_missing))
    query = query.order_by(desc(Game.rank_score), desc(Game.metrix_score)).limit(target)
    games = list(db.scalars(query).all())

    client = HltbClient()
    imported = 0
    skipped = 0
    repaired_covers = 0
    for game in games:
        if repair_missing_cover(game):
            repaired_covers += 1
            imported += 1
            db.add(game)
            db.commit()

        match = await client.search(game.title, release_year=game.release_year)
        if not match:
            skipped += 1
        elif apply_hltb_match(game, match, refresh_existing=refresh_existing):
            imported += 1
            db.add(game)
            db.commit()
        else:
            skipped += 1
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    return {"imported": imported, "skipped": skipped, "repaired_covers": repaired_covers}
