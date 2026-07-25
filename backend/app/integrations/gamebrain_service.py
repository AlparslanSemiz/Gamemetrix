"""Optional GameBrain metadata adapter.

The free plan is non-commercial and backlink-gated, and persistent storage
needs written permission. Configuration therefore requires all three explicit
credential/license flags.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from ..config import get_settings
from .rate_limiter import get_rate_limiter
from .title_matching import title_match_quality
from .types import NormalizedGame, normalize_game_modes


GAMEBRAIN_GAMES_URL = "https://api.gamebrain.co/v1/games"
_STEAM_URL_RE = re.compile(r"store\.steampowered\.com/app/(\d+)", re.IGNORECASE)


def _named_values(raw: dict, key: str) -> list[str]:
    values = raw.get(key)
    if not isinstance(values, list):
        return []
    output: list[str] = []
    for value in values:
        name = value.get("name") if isinstance(value, dict) else value
        if isinstance(name, str) and name.strip() and name.strip() not in output:
            output.append(name.strip())
    return output


def _platform(value: str) -> str:
    lowered = value.casefold()
    if lowered in {"windows", "microsoft windows"}:
        return "PC"
    if "playstation" in lowered:
        match = re.search(r"(\d+)", value)
        return f"PlayStation {match.group(1)}" if match else "PlayStation"
    return value


def _release_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class GameBrainService:
    def is_configured(self) -> bool:
        return get_settings().gamebrain_configured()

    async def search_game(
        self,
        title: str,
        *,
        release_year: int | None = None,
    ) -> NormalizedGame | None:
        cfg = get_settings()
        if not cfg.gamebrain_configured() or get_rate_limiter().remaining("GameBrain") < 2:
            return None
        if not await get_rate_limiter().acquire("GameBrain"):
            return None
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                GAMEBRAIN_GAMES_URL,
                params={"query": title, "limit": 10, "offset": 0},
                headers={"x-api-key": cfg.GAMEBRAIN_API_KEY},
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("results") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                return None
            candidates = [row for row in rows if isinstance(row, dict) and row.get("id")]
            if release_year:
                same_year = [
                    row for row in candidates
                    if (
                        row.get("year") == release_year
                        or (
                            _release_date(row.get("release_date"))
                            and _release_date(row.get("release_date")).year == release_year
                        )
                    )
                ]
                if same_year:
                    candidates = same_year
            if not candidates:
                return None
            best = max(
                candidates,
                key=lambda row: title_match_quality(title, str(row.get("name") or "")),
            )
            if title_match_quality(title, str(best.get("name") or "")) <= 0:
                return None
            return await self.get_detail(str(best["id"]), client=client)

    async def get_detail(
        self,
        game_id: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> NormalizedGame | None:
        cfg = get_settings()
        if not cfg.gamebrain_configured() or not await get_rate_limiter().acquire("GameBrain"):
            return None
        owns_client = client is None
        active_client = client or httpx.AsyncClient(timeout=15)
        try:
            response = await active_client.get(
                f"{GAMEBRAIN_GAMES_URL}/{game_id}",
                headers={"x-api-key": cfg.GAMEBRAIN_API_KEY},
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if owns_client:
                await active_client.aclose()
        raw = payload.get("game") if isinstance(payload, dict) and isinstance(payload.get("game"), dict) else payload
        return self.normalize_detail(raw) if isinstance(raw, dict) else None

    def normalize_detail(self, raw: dict) -> NormalizedGame:
        raw_id = str(raw.get("id") or "")
        name = str(raw.get("name") or "").strip()
        platforms = list(dict.fromkeys(
            _platform(value) for value in _named_values(raw, "platforms")
        ))
        stores = raw.get("official_stores") if isinstance(raw.get("official_stores"), list) else []
        steam_app_id: int | None = None
        for store in stores:
            if not isinstance(store, dict):
                continue
            match = _STEAM_URL_RE.search(str(store.get("url") or ""))
            if match:
                steam_app_id = int(match.group(1))
                break
        screenshots = [
            value for value in (raw.get("screenshots") or [])
            if isinstance(value, str)
        ]
        normalized_raw: dict[str, object] = {
            "screenshots": screenshots,
            "gamebrain_url": raw.get("link"),
        }
        if steam_app_id:
            normalized_raw["steam_app_id"] = steam_app_id
        return NormalizedGame(
            source="GameBrain",
            external_id=raw_id,
            name=name,
            external_url=str(raw.get("link") or "") or None,
            release_date=_release_date(raw.get("release_date")),
            platforms=platforms,
            genres=_named_values(raw, "genres"),
            game_modes=list(normalize_game_modes(_named_values(raw, "play_modes"))),
            developer=str(raw.get("developer") or "").strip() or None,
            publisher=str(raw.get("publisher") or "").strip() or None,
            summary=str(raw.get("short_description") or "").strip() or None,
            cover_url=str(raw.get("image") or "").strip() or None,
            # GameBrain ratings remain supplementary and never enter GameMetrix.
            score=None,
            score_count=None,
            raw=normalized_raw,
        )


gamebrain_service = GameBrainService()
