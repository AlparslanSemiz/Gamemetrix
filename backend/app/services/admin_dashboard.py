from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    AnalyticsEvent,
    ExternalId,
    Game,
    RatingSnapshot,
    SourceSnapshot,
    User,
    VisitEvent,
)

_ACTIVE_ACCOUNT_WINDOW = timedelta(days=30)
_RECENT_CATALOG_ADDITION_LIMIT = 25
_TOP_PAGE_LIMIT = 10
_RECENT_VISIT_LIMIT = 20
_RECENT_IP_LIMIT = 100


def build_admin_dashboard(db: Session, days: int) -> dict[str, object]:
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    traffic = _traffic_metrics(db, days=days, now=now, since=since)
    return {
        "catalog": _catalog_metrics(db, days=days, now=now),
        "accounts": _account_metrics(db, now),
        "acquisition": _acquisition_metrics(
            db,
            since=since,
            unique_visitors=int(traffic["unique_visitors"]),
        ),
        "traffic": traffic,
    }


def _catalog_metrics(
    db: Session,
    *,
    days: int,
    now: datetime,
) -> dict[str, object]:
    indexable_games = _scalar_count(
        db,
        select(func.count(Game.id)).where(Game.seo_indexable.is_(True)),
    )
    seo_exclusions = {
        reason or "indexable": count
        for reason, count in db.execute(
            select(Game.seo_exclusion_reason, func.count(Game.id))
            .group_by(Game.seo_exclusion_reason)
        ).all()
    }
    return {
        "total_games": _scalar_count(db, select(func.count(Game.id))),
        "rankable_games": _scalar_count(
            db,
            select(func.count(Game.id)).where(Game.is_rankable.is_(True)),
        ),
        "seo_indexable_games": indexable_games,
        "sitemap_game_pages": min(indexable_games, get_settings().SEO_INDEX_LIMIT),
        "seo_exclusions": seo_exclusions,
        "non_game_rows": _scalar_count(
            db,
            select(func.count(Game.id)).where(Game.content_type != "game"),
        ),
        "rating_snapshots": _scalar_count(db, select(func.count(RatingSnapshot.id))),
        "source_snapshots": _scalar_count(db, select(func.count(SourceSnapshot.id))),
        "additions": _catalog_additions(db, days=days, now=now),
    }


def _catalog_additions(
    db: Session,
    *,
    days: int,
    now: datetime,
) -> dict[str, object]:
    tracked_games = (
        Game.content_type == "game",
        Game.catalog_added_at.is_not(None),
    )
    return {
        "days": days,
        "last_24h": _scalar_count(
            db,
            select(func.count(Game.id)).where(
                *tracked_games,
                Game.catalog_added_at >= now - timedelta(hours=24),
            ),
        ),
        "last_7d": _scalar_count(
            db,
            select(func.count(Game.id)).where(
                *tracked_games,
                Game.catalog_added_at >= now - timedelta(days=7),
            ),
        ),
        "last_30d": _scalar_count(
            db,
            select(func.count(Game.id)).where(
                *tracked_games,
                Game.catalog_added_at >= now - timedelta(days=30),
            ),
        ),
        "untracked_games": _scalar_count(
            db,
            select(func.count(Game.id)).where(
                Game.content_type == "game",
                Game.catalog_added_at.is_(None),
            ),
        ),
        "daily": _daily_catalog_additions(db, days=days, now=now),
        "recent": _recent_catalog_additions(db),
    }


def _daily_catalog_additions(
    db: Session,
    *,
    days: int,
    now: datetime,
) -> list[dict[str, object]]:
    since = now - timedelta(days=days)
    added_day = func.date(Game.catalog_added_at).label("added_day")
    counts = {
        day.isoformat(): int(count)
        for day, count in db.execute(
            select(added_day, func.count(Game.id))
            .where(
                Game.content_type == "game",
                Game.catalog_added_at.is_not(None),
                Game.catalog_added_at >= since,
            )
            .group_by(added_day)
        ).all()
    }
    return _fill_daily_catalog_addition_gaps(counts, days=days, now=now)


def _fill_daily_catalog_addition_gaps(
    counts: dict[str, int],
    *,
    days: int,
    now: datetime,
) -> list[dict[str, object]]:
    return [
        {
            "date": (now - timedelta(days=offset)).date().isoformat(),
            "count": counts.get(
                (now - timedelta(days=offset)).date().isoformat(),
                0,
            ),
        }
        for offset in range(days - 1, -1, -1)
    ]


def _recent_catalog_additions(db: Session) -> list[dict[str, object]]:
    games = list(
        db.execute(
            select(
                Game.id,
                Game.title,
                Game.slug,
                Game.catalog_added_at,
            )
            .where(
                Game.content_type == "game",
                Game.catalog_added_at.is_not(None),
            )
            .order_by(Game.catalog_added_at.desc(), Game.id.desc())
            .limit(_RECENT_CATALOG_ADDITION_LIMIT)
        ).all()
    )
    if not games:
        return []

    game_ids = [int(row.id) for row in games]
    sources_by_game: dict[int, list[str]] = {game_id: [] for game_id in game_ids}
    for game_id, source in db.execute(
        select(ExternalId.game_id, ExternalId.source)
        .where(ExternalId.game_id.in_(game_ids))
        .order_by(ExternalId.game_id, ExternalId.source)
    ).all():
        if source not in sources_by_game[game_id]:
            sources_by_game[game_id].append(source)

    return [
        {
            "id": row.id,
            "title": row.title,
            "slug": row.slug,
            "added_at": row.catalog_added_at.isoformat(),
            "sources": sources_by_game[row.id],
        }
        for row in games
    ]


def _account_metrics(db: Session, now: datetime) -> dict[str, int]:
    return {
        "registered": _scalar_count(db, select(func.count(User.id))),
        "verified": _scalar_count(
            db,
            select(func.count(User.id)).where(User.email_verified_at.is_not(None)),
        ),
        "active_30d": _scalar_count(
            db,
            select(func.count(User.id)).where(
                User.last_login_at >= now - _ACTIVE_ACCOUNT_WINDOW
            ),
        ),
    }


def _traffic_metrics(
    db: Session,
    *,
    days: int,
    now: datetime,
    since: datetime,
) -> dict[str, object]:
    today_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    cfg = get_settings()
    return {
        "days": days,
        "total_visits_all_time": _scalar_count(
            db,
            select(func.count(VisitEvent.id)),
        ),
        "total_unique_visitors": _scalar_count(
            db,
            select(func.count(func.distinct(VisitEvent.visitor_id_hash))),
        ),
        "total_unique_ips": _scalar_count(
            db,
            select(func.count(func.distinct(VisitEvent.ip_hash))).where(
                VisitEvent.ip_hash.is_not(None)
            ),
        ),
        "total_sessions_all_time": _scalar_count(
            db,
            select(func.count(func.distinct(VisitEvent.session_id_hash))).where(
                VisitEvent.session_id_hash.is_not(None)
            ),
        ),
        "known_account_visitors": _scalar_count(
            db,
            select(func.count(func.distinct(VisitEvent.user_id))).where(
                VisitEvent.user_id.is_not(None)
            ),
        ),
        "total_visits": _scalar_count(
            db,
            select(func.count(VisitEvent.id)).where(VisitEvent.created_at >= since),
        ),
        "unique_visitors": _scalar_count(
            db,
            select(func.count(func.distinct(VisitEvent.visitor_id_hash))).where(
                VisitEvent.created_at >= since
            ),
        ),
        "unique_ips": _scalar_count(
            db,
            select(func.count(func.distinct(VisitEvent.ip_hash))).where(
                VisitEvent.created_at >= since,
                VisitEvent.ip_hash.is_not(None),
            ),
        ),
        "visits_today": _scalar_count(
            db,
            select(func.count(VisitEvent.id)).where(
                VisitEvent.created_at >= today_start
            ),
        ),
        "unique_today": _scalar_count(
            db,
            select(func.count(func.distinct(VisitEvent.visitor_id_hash))).where(
                VisitEvent.created_at >= today_start
            ),
        ),
        "top_pages": _top_pages(db, since),
        "daily": _daily_traffic(db, days=days, now=now, since=since),
        "recent_visits": _recent_visits(db),
        "recent_ips": _recent_ips(db),
        "tracking": {
            "bot_filtering": True,
            "raw_ip_enabled": cfg.ANALYTICS_STORE_RAW_IP,
            "trusted_proxy_headers": cfg.ANALYTICS_TRUST_PROXY_HEADERS,
            "raw_ip_retention_days": cfg.ANALYTICS_RAW_IP_RETENTION_DAYS,
        },
    }


def _top_pages(db: Session, since: datetime) -> list[dict[str, object]]:
    visit_count = func.count(VisitEvent.id).label("visits")
    return [
        {"path": path, "visits": visits}
        for path, visits in db.execute(
            select(VisitEvent.path, visit_count)
            .where(VisitEvent.created_at >= since)
            .group_by(VisitEvent.path)
            .order_by(desc(visit_count))
            .limit(_TOP_PAGE_LIMIT)
        ).all()
    ]


def _daily_traffic(
    db: Session,
    *,
    days: int,
    now: datetime,
    since: datetime,
) -> list[dict[str, object]]:
    visit_day = func.date(VisitEvent.created_at).label("visit_day")
    counts = {
        day.isoformat(): {"visits": visits, "visitors": visitors}
        for day, visits, visitors in db.execute(
            select(
                visit_day,
                func.count(VisitEvent.id),
                func.count(func.distinct(VisitEvent.visitor_id_hash)),
            )
            .where(VisitEvent.created_at >= since)
            .group_by(visit_day)
        ).all()
    }
    rows: list[dict[str, object]] = []
    for offset in range(days - 1, -1, -1):
        date_key = (now - timedelta(days=offset)).date().isoformat()
        count = counts.get(date_key, {"visits": 0, "visitors": 0})
        rows.append(
            {
                "date": date_key,
                "visits": int(count["visits"]),
                "visitors": int(count["visitors"]),
            }
        )
    return rows


def _recent_visits(db: Session) -> list[dict[str, object]]:
    return [
        {
            "path": event.path,
            "created_at": event.created_at.isoformat(),
            "visitor": event.visitor_id_hash[:10],
            "session": event.session_id_hash[:10] if event.session_id_hash else None,
            "ip": event.ip_address,
            "ip_fingerprint": event.ip_hash[:10] if event.ip_hash else None,
            "country": event.country_code,
            "language": event.language,
            "timezone": event.timezone,
            "user_agent": event.user_agent,
            "referrer": event.referrer,
            "screen": _screen_size(event),
            "account": account_email,
        }
        for event, account_email in db.execute(
            select(VisitEvent, User.email)
            .outerjoin(User, User.id == VisitEvent.user_id)
            .order_by(VisitEvent.created_at.desc())
            .limit(_RECENT_VISIT_LIMIT)
        ).all()
    ]


def _screen_size(event: VisitEvent) -> str | None:
    if not event.screen_width or not event.screen_height:
        return None
    return f"{event.screen_width}x{event.screen_height}"


def _recent_ips(db: Session) -> list[dict[str, object]]:
    visit_count = func.count(VisitEvent.id).label("visits")
    first_seen = func.min(VisitEvent.created_at).label("first_seen")
    last_seen = func.max(VisitEvent.created_at).label("last_seen")
    return [
        {
            "ip": raw_ip,
            "fingerprint": ip_hash[:10],
            "country": country,
            "visits": visits,
            "first_seen": first_visit.isoformat(),
            "last_seen": last_visit.isoformat(),
        }
        for ip_hash, raw_ip, country, visits, first_visit, last_visit in db.execute(
            select(
                VisitEvent.ip_hash,
                func.max(VisitEvent.ip_address),
                func.max(VisitEvent.country_code),
                visit_count,
                first_seen,
                last_seen,
            )
            .where(VisitEvent.ip_hash.is_not(None))
            .group_by(VisitEvent.ip_hash)
            .order_by(desc(last_seen))
            .limit(_RECENT_IP_LIMIT)
        ).all()
    ]


def _acquisition_metrics(
    db: Session,
    *,
    since: datetime,
    unique_visitors: int,
) -> dict[str, object]:
    organic_filter = VisitEvent.referrer.ilike("%google.%")
    organic_sessions = _scalar_count(
        db,
        select(func.count(func.distinct(VisitEvent.session_id_hash))).where(
            VisitEvent.created_at >= since,
            organic_filter,
            VisitEvent.session_id_hash.is_not(None),
        ),
    )
    organic_visitors = _scalar_count(
        db,
        select(func.count(func.distinct(VisitEvent.visitor_id_hash))).where(
            VisitEvent.created_at >= since,
            organic_filter,
        ),
    )
    event_counts = {
        event_type: count
        for event_type, count in db.execute(
            select(AnalyticsEvent.event_type, func.count(AnalyticsEvent.id))
            .where(AnalyticsEvent.created_at >= since)
            .group_by(AnalyticsEvent.event_type)
        ).all()
    }
    organic_signups = _organic_signup_count(db, since, organic_filter)
    signup_count = int(event_counts.get("signup_completed", 0))
    return {
        "organic_sessions": organic_sessions,
        "organic_visitors": organic_visitors,
        "organic_signups": organic_signups,
        "organic_signup_conversion": _percentage(
            organic_signups,
            organic_visitors,
        ),
        "signup_conversion": _percentage(signup_count, unique_visitors),
        "outbound_store_clicks": int(event_counts.get("store_outbound", 0)),
        "organic_landing_pages": _organic_landing_pages(
            db,
            since,
            organic_filter,
        ),
        "repeat_visitors": _repeat_visitor_count(db, since),
        "events": event_counts,
    }


def _organic_landing_pages(
    db: Session,
    since: datetime,
    organic_filter: object,
) -> list[dict[str, object]]:
    visit_count = func.count(VisitEvent.id).label("visits")
    return [
        {"path": path, "visits": visits}
        for path, visits in db.execute(
            select(VisitEvent.path, visit_count)
            .where(VisitEvent.created_at >= since, organic_filter)
            .group_by(VisitEvent.path)
            .order_by(visit_count.desc())
            .limit(_TOP_PAGE_LIMIT)
        ).all()
    ]


def _repeat_visitor_count(db: Session, since: datetime) -> int:
    return _scalar_count(
        db,
        select(func.count()).select_from(
            select(VisitEvent.visitor_id_hash)
            .where(VisitEvent.created_at >= since)
            .group_by(VisitEvent.visitor_id_hash)
            .having(func.count(func.distinct(VisitEvent.session_id_hash)) > 1)
            .subquery()
        ),
    )


def _organic_signup_count(
    db: Session,
    since: datetime,
    organic_filter: object,
) -> int:
    organic_visitor_hashes = (
        select(VisitEvent.visitor_id_hash)
        .where(VisitEvent.created_at >= since, organic_filter)
        .distinct()
    )
    return _scalar_count(
        db,
        select(func.count(AnalyticsEvent.id)).where(
            AnalyticsEvent.created_at >= since,
            AnalyticsEvent.event_type == "signup_completed",
            AnalyticsEvent.visitor_id_hash.in_(organic_visitor_hashes),
        ),
    )


def _percentage(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _scalar_count(db: Session, statement: object) -> int:
    return int(db.scalar(statement) or 0)
