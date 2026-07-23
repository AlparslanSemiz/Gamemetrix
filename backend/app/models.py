from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import game_signals
from .database import Base
from .integrations.source_registry import PC_PLATFORM_KEYS, applicable_for_game


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    summary_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cover_url: Mapped[str] = mapped_column(String(500), nullable=False)
    release_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    release_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    early_access_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    official_release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    metacritic_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ratings_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prices_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False, default="game")
    metrix_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    rank_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, index=True)
    is_rankable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seo_indexable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    seo_exclusion_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    seo_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    critic_score: Mapped[float] = mapped_column(Float, nullable=False)
    user_score: Mapped[float] = mapped_column(Float, nullable=False)
    genres: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    platforms: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_scores: Mapped[list[dict[str, str | float | int]]] = mapped_column(
        JSON,
        nullable=False,
    )
    developer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Authoritative Steam App ID. Without it the app had to scrape the id back out
    # of the cover URL, which silently failed for any game whose art came from
    # IGDB/GOG/PlayStation rather than Steam.
    steam_app_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    game_modes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    playtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hltb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hltb_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hltb_main_story_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hltb_main_extra_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hltb_completionist_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hltb_all_styles_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hltb_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_endless: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    endless_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proton_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    proton_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    award_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    award_nominations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    goty_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    awards: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    screenshots: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    system_requirements: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    dlcs: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    similar_games: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    franchise: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship("PriceSnapshot", back_populates="game", cascade="all, delete-orphan", lazy="select")

    @property
    def is_pc_applicable(self) -> bool:
        return any(p.lower() in PC_PLATFORM_KEYS for p in self.platforms if isinstance(p, str))

    @property
    def applicable_primary_sources(self) -> frozenset[str]:
        return applicable_for_game([p for p in self.platforms if isinstance(p, str)])

    @property
    def applicable_sources(self) -> list[str]:
        return sorted(self.applicable_primary_sources)

    @property
    def applicable_source_count(self) -> int:
        return len(self.applicable_primary_sources)

    @property
    def live_primary_source_count(self) -> int:
        return game_signals.live_primary_source_count(
            self.source_scores, self.applicable_primary_sources
        )

    @property
    def confidence_level(self) -> str:
        return game_signals.confidence_level(
            self.source_scores, self.applicable_primary_sources
        )

    @property
    def data_strength(self) -> str:
        return game_signals.data_strength(self.confidence_level)

    @property
    def rank_exclusion_reason(self) -> str | None:
        if self.content_type != "game":
            return "not_rankable_content_type"
        if self.is_rankable:
            return None
        if self.confidence_level == "Catalog":
            return "catalog_only"
        if self.confidence_level == "Limited":
            return "insufficient_rating_data"
        return None

    @property
    def score_profile(self) -> str:
        return game_signals.score_profile(self.source_scores)

    @property
    def popularity_label(self) -> str | None:
        return game_signals.popularity_label(self.source_scores)


class ExternalId(Base):
    """Maps a GameMetrix game to its identifier in an external source (IGDB, RAWG, Steam, etc.)."""

    __tablename__ = "external_ids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    external_slug: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 0.0–1.0: how confident we are the mapping is correct
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RatingSnapshot(Base):
    """
    Immutable record of a score fetched from an external rating source.
    Append-only; latest per (game_id, source) is the authoritative score.
    """

    __tablename__ = "rating_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_normalized: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critic_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_critic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceSnapshot(Base):
    """Raw API response audit log — debug/replay only, never used for scoring."""

    __tablename__ = "source_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(300), nullable=False)
    query: Mapped[str | None] = mapped_column(String(300), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VisitEvent(Base):
    """Page-view event with stable hashes and optional short-lived raw network data."""

    __tablename__ = "visit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    visitor_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    language: Mapped[str | None] = mapped_column(String(35), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    referrer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    screen_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    screen_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class User(Base):
    """Normal product account. Admin credentials intentionally live outside this table."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_oauth_provider_subject"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountSession(Base):
    __tablename__ = "account_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccountToken(Base):
    __tablename__ = "account_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserCollection(Base):
    __tablename__ = "user_collections"
    __table_args__ = (
        UniqueConstraint("user_id", "game_id", "collection_type", name="uq_user_collection_game_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    alert_min_discount: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    alert_min_score: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    alert_upcoming_days: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    email_digest_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    marketing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserAlertState(Base):
    __tablename__ = "user_alert_states"
    __table_args__ = (
        UniqueConstraint("user_id", "alert_key", name="uq_user_alert_state_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_key: Mapped[str] = mapped_column(String(240), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint", name="uq_notification_delivery_fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="email")
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    visitor_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class PriceSnapshot(Base):
    """Current + historical price data per game/store, sourced from ITAD or CheapShark."""

    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    external_price_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    store: Mapped[str] = mapped_column(String(100), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    region: Mapped[str] = mapped_column(String(20), nullable=False, default="US")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    list_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    sale_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    historical_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    historical_low_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sale_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_free: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_subscription_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subscription_service: Mapped[str | None] = mapped_column(String(100), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    itad_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    game: Mapped["Game"] = relationship("Game", back_populates="price_snapshots")


class ApiRequestBudget(Base):
    """Persistent daily request counter for one upstream API source."""

    __tablename__ = "api_request_budgets"
    __table_args__ = (
        UniqueConstraint("source", "bucket_date", name="uq_api_request_budgets_source_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApiRequestWindow(Base):
    """Persistent provider quota counter for non-daily fixed windows."""

    __tablename__ = "api_request_windows"
    __table_args__ = (
        UniqueConstraint("source", "window_kind", "window_start", name="uq_api_request_window"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    window_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminAuditLog(Base):
    """Who did what on the admin surface: every /admin/* request plus login attempts."""

    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    query: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class DataFillRun(Base):
    """Audit row for full catalog/data fill runs."""

    __tablename__ = "data_fill_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    force: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    target_total: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

