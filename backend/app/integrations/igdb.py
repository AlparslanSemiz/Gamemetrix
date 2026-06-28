from datetime import UTC, datetime, timedelta

import httpx

from ..config import get_settings
from .types import ExternalScore


_TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_IGDB_GAMES_URL = "https://api.igdb.com/v4/games"
_HTTP_TIMEOUT = 12

_cached_token: str | None = None
_token_expires_at: datetime | None = None


async def _get_access_token(client_id: str, client_secret: str) -> str:
    global _cached_token, _token_expires_at

    if _cached_token and _token_expires_at and datetime.now(UTC) < _token_expires_at:
        return _cached_token

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        response = await client.post(
            _TWITCH_TOKEN_URL,
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
        )
        response.raise_for_status()

    payload = response.json()
    _cached_token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 3600))
    # Expire 60 seconds early to avoid using a token that's about to expire.
    _token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in - 60)
    return _cached_token


def _unavailable(detail: str) -> ExternalScore:
    return ExternalScore(source="IGDB", score=0, status="unavailable", detail=detail)


def _pick_score(game: dict) -> float | None:
    # IGDB is our user-community signal: prefer user rating over aggregated critic rating.
    return game.get("rating") or game.get("total_rating") or game.get("aggregated_rating")


def _pick_review_count(game: dict) -> int:
    return int(
        game.get("rating_count")
        or game.get("total_rating_count")
        or game.get("aggregated_rating_count")
        or 0
    )


async def get_igdb_score(title: str) -> ExternalScore:
    cfg = get_settings()
    if not cfg.igdb_configured():
        return _unavailable("Set IGDB_CLIENT_ID and IGDB_CLIENT_SECRET to enable IGDB.")

    token = await _get_access_token(cfg.IGDB_CLIENT_ID, cfg.IGDB_CLIENT_SECRET)
    query = (
        "fields id,slug,url,name,rating,rating_count,aggregated_rating,aggregated_rating_count,"
        "total_rating,total_rating_count,first_release_date,genres.name,platforms.name,"
        "involved_companies.company.name,involved_companies.developer,involved_companies.publisher,"
        "cover.url,screenshots.url,summary; "
        f'search "{title}"; '
        "where version_parent = null; "
        "limit 1;"
    )
    headers = {
        "Client-ID": cfg.IGDB_CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        response = await client.post(_IGDB_GAMES_URL, headers=headers, content=query)
        if response.status_code == 429:
            return _unavailable("IGDB rate limit hit — retry later.")
        response.raise_for_status()

    games = response.json()
    if not games:
        return _unavailable("IGDB returned no matching game.")

    game = games[0]
    raw_score = _pick_score(game)
    if raw_score is None:
        return _unavailable("IGDB game has no rating field yet.")

    review_count = _pick_review_count(game)
    return ExternalScore(
        source="IGDB",
        score=round(float(raw_score), 1),
        review_count=review_count,
        detail=f"IGDB user rating ({review_count} ratings)" if review_count else "IGDB user rating",
        raw={
            "igdb_id": int(game.get("id") or 0),
            "igdb_slug": game.get("slug"),
            "igdb_url": game.get("url"),
            "response": game,
        },
    )
