import os
from datetime import UTC, datetime, timedelta

import httpx

from .types import ExternalScore


_cached_token: str | None = None
_token_expires_at: datetime | None = None


async def _get_access_token(client_id: str, client_secret: str) -> str:
    global _cached_token, _token_expires_at

    if _cached_token and _token_expires_at and datetime.now(UTC) < _token_expires_at:
        return _cached_token

    params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }

    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.post("https://id.twitch.tv/oauth2/token", params=params)
        response.raise_for_status()

    payload = response.json()
    _cached_token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 3600))
    _token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in - 60)
    return _cached_token


async def get_igdb_score(title: str) -> ExternalScore:
    client_id = os.getenv("IGDB_CLIENT_ID")
    client_secret = os.getenv("IGDB_CLIENT_SECRET")

    if not client_id or not client_secret:
        return ExternalScore(
            source="IGDB",
            score=0,
            status="unavailable",
            detail="Set IGDB_CLIENT_ID and IGDB_CLIENT_SECRET to enable IGDB.",
        )

    token = await _get_access_token(client_id, client_secret)
    body = (
        "fields name,rating,rating_count,aggregated_rating,aggregated_rating_count,total_rating,total_rating_count; "
        f'search "{title}"; '
        "where version_parent = null; "
        "limit 1;"
    )

    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
    }

    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.post(
            "https://api.igdb.com/v4/games",
            headers=headers,
            content=body,
        )
        response.raise_for_status()

    games = response.json()
    if not games:
        return ExternalScore(
            source="IGDB",
            score=0,
            status="unavailable",
            detail="IGDB returned no matching game.",
        )

    game = games[0]

    # IGDB is our niche/user signal: prefer user rating first.
    raw_score = (
        game.get("rating")
        or game.get("total_rating")
        or game.get("aggregated_rating")
    )
    if raw_score is None:
        return ExternalScore(
            source="IGDB",
            score=0,
            status="unavailable",
            detail="IGDB game has no rating field yet.",
        )

    review_count = int(
        game.get("rating_count")
        or game.get("total_rating_count")
        or game.get("aggregated_rating_count")
        or 0
    )

    return ExternalScore(
        source="IGDB",
        score=round(float(raw_score), 1),
        review_count=review_count,
        detail=f"IGDB user rating ({review_count} ratings)" if review_count else "IGDB user rating",
    )
