import re
from datetime import UTC, date, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ExternalId, Game, infer_content_type
from ..services.deduplication import find_existing_duplicate, merge_game_data
from ..services.rawg_import import platform_family
from .igdb import _get_access_token
from .sync import calculate_metrix_score, compute_rank_fields


IGDB_GAMES_URL = "https://api.igdb.com/v4/games"
NINTENDO_PLATFORM_IDS = [
    130,  # Nintendo Switch
    508,  # Nintendo Switch 2
    41,   # Wii U
    5,    # Wii
    37,   # Nintendo 3DS
    137,  # New Nintendo 3DS
    20,   # Nintendo DS
    159,  # Nintendo DSi
    21,   # Nintendo GameCube
    4,    # Nintendo 64
    19,   # SNES
    18,   # NES
    24,   # Game Boy Advance
    22,   # Game Boy Color
    33,   # Game Boy
]
_HTTP_TIMEOUT = 20


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "game"


def _igdb_image_url(url: str | None, size: str) -> str | None:
    if not url:
        return None
    return url.replace("//", "https://").replace("t_thumb", size)


def _igdb_date(timestamp: int | None) -> date:
    if not timestamp:
        return date(1970, 1, 1)
    try:
        return datetime.fromtimestamp(int(timestamp), tz=UTC).date()
    except (OSError, ValueError):
        return date(1970, 1, 1)


def _company_names(raw_game: dict) -> tuple[str | None, str | None]:
    developer: str | None = None
    publisher: str | None = None
    for item in raw_game.get("involved_companies") or []:
        if not isinstance(item, dict):
            continue
        name = (item.get("company") or {}).get("name")
        if not name:
            continue
        if item.get("developer") and not developer:
            developer = name
        if item.get("publisher") and not publisher:
            publisher = name
    return developer, publisher


def _score_fields(raw_game: dict) -> tuple[float, int, float, float]:
    user_score = float(raw_game.get("rating") or raw_game.get("total_rating") or raw_game.get("aggregated_rating") or 0)
    critic_score = float(raw_game.get("aggregated_rating") or raw_game.get("total_rating") or raw_game.get("rating") or 0)
    review_count = int(
        raw_game.get("rating_count")
        or raw_game.get("total_rating_count")
        or raw_game.get("aggregated_rating_count")
        or 0
    )
    score = float(raw_game.get("total_rating") or raw_game.get("rating") or raw_game.get("aggregated_rating") or 0)
    return score, review_count, critic_score, user_score


def _game_from_igdb(raw_game: dict) -> Game:
    title = raw_game.get("name") or "Untitled Game"
    released = _igdb_date(raw_game.get("first_release_date"))
    cover_url = _igdb_image_url((raw_game.get("cover") or {}).get("url"), "t_cover_big_2x") or ""
    screenshots = [
        url
        for item in raw_game.get("screenshots") or []
        if (url := _igdb_image_url(item.get("url") if isinstance(item, dict) else None, "t_screenshot_big"))
    ]
    genres = [
        item["name"]
        for item in raw_game.get("genres") or []
        if isinstance(item, dict) and item.get("name")
    ]
    platforms = sorted({
        platform_family(item["name"])
        for item in raw_game.get("platforms") or []
        if isinstance(item, dict) and item.get("name")
    })
    developer, publisher = _company_names(raw_game)
    score, review_count, critic_score, user_score = _score_fields(raw_game)
    source_scores = []
    if score > 0:
        source_scores.append({
            "source": "IGDB",
            "score": round(score, 1),
            "scale": 100,
            "status": "live",
            "review_count": review_count,
            "detail": "IGDB total rating from Nintendo catalog import.",
        })
    metrix_score = calculate_metrix_score(source_scores)
    game = Game(
        title=title,
        slug=f"{_slugify(title)}-{raw_game.get('id') or _slugify(title)}",
        summary=raw_game.get("summary") or f"{title} was imported from the IGDB Nintendo catalog.",
        cover_url=cover_url,
        release_date=released,
        release_year=released.year,
        official_release_date=released if released.year > 1970 else None,
        metacritic_score=None,
        image_url=cover_url or None,
        metrix_score=metrix_score,
        critic_score=critic_score,
        user_score=user_score,
        genres=genres or ["Uncategorized"],
        platforms=platforms or ["Nintendo"],
        source_scores=source_scores,
        developer=developer,
        publisher=publisher,
        screenshots=screenshots,
    )
    game.content_type = infer_content_type(game)
    game.rank_score, game.is_rankable, _ = compute_rank_fields(game)
    return game


def _upsert_igdb_external_id(db: Session, game: Game, raw_game: dict) -> None:
    igdb_id = str(raw_game.get("id") or "")
    if not igdb_id:
        return
    now = datetime.now(UTC)
    existing = db.scalar(
        select(ExternalId).where(
            ExternalId.game_id == game.id,
            ExternalId.source == "IGDB",
        )
    )
    if existing:
        existing.external_id = igdb_id
        existing.external_slug = raw_game.get("slug")
        existing.external_url = raw_game.get("url")
        existing.updated_at = now
        return
    db.add(ExternalId(
        game_id=game.id,
        source="IGDB",
        external_id=igdb_id,
        external_slug=raw_game.get("slug"),
        external_url=raw_game.get("url"),
        confidence=0.9,
        is_primary=True,
        created_at=now,
        updated_at=now,
    ))


def _existing_by_igdb_id(db: Session, raw_game: dict) -> Game | None:
    igdb_id = str(raw_game.get("id") or "")
    if not igdb_id:
        return None
    external = db.scalar(
        select(ExternalId).where(
            ExternalId.source == "IGDB",
            ExternalId.external_id == igdb_id,
        )
    )
    return db.get(Game, external.game_id) if external else None


async def import_igdb_nintendo_games(db: Session, target: int = 500, page_size: int = 50) -> dict[str, int]:
    cfg = get_settings()
    if not cfg.igdb_configured():
        raise RuntimeError("IGDB_CLIENT_ID and IGDB_CLIENT_SECRET are not configured.")

    try:
        token = await _get_access_token(cfg.IGDB_CLIENT_ID, cfg.IGDB_CLIENT_SECRET)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise RuntimeError("IGDB credentials were rejected. Add valid Twitch/IGDB credentials to backend/.env and restart.") from exc
        raise

    imported = 0
    skipped = 0
    headers = {
        "Client-ID": cfg.IGDB_CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }
    fields = (
        "fields id,name,slug,url,first_release_date,rating,rating_count,"
        "aggregated_rating,aggregated_rating_count,total_rating,total_rating_count,"
        "platforms.name,genres.name,cover.url,screenshots.url,summary,"
        "involved_companies.company.name,involved_companies.developer,"
        "involved_companies.publisher; "
    )

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for platform_id in NINTENDO_PLATFORM_IDS:
            offset = 0
            while imported < target:
                body = (
                    fields +
                    f"where platforms = {platform_id} & version_parent = null & total_rating_count > 0; "
                    "sort total_rating_count desc; "
                    f"limit {min(page_size, target - imported)}; offset {offset};"
                )
                response = await client.post(IGDB_GAMES_URL, headers=headers, content=body)
                if response.status_code in (401, 403):
                    raise RuntimeError("IGDB credentials were rejected. Add valid Twitch/IGDB credentials to backend/.env and restart.")
                response.raise_for_status()
                results = response.json()
                if not results:
                    break

                for raw_game in results:
                    game = _game_from_igdb(raw_game)
                    existing = _existing_by_igdb_id(db, raw_game)
                    if existing is None:
                        existing = db.scalar(select(Game).where(Game.slug == game.slug))
                    if existing is None:
                        existing = db.scalar(select(Game).where(func.lower(Game.title) == game.title.lower()))
                    if existing is None:
                        existing = find_existing_duplicate(db, game)

                    if existing:
                        merge_game_data(existing, game)
                        db.add(existing)
                        db.flush()
                        _upsert_igdb_external_id(db, existing, raw_game)
                        skipped += 1
                        continue

                    db.add(game)
                    db.flush()
                    _upsert_igdb_external_id(db, game, raw_game)
                    imported += 1

                db.commit()
                offset += page_size
                if len(results) < page_size:
                    break
            if imported >= target:
                break

    return {"imported": imported, "skipped": skipped}
