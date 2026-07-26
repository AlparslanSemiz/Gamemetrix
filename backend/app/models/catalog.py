"""Catalog tables: games and the source data attached to them."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import game_signals
from ..database import Base
from ..integrations.source_registry import PC_PLATFORM_KEYS, applicable_for_game


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    summary_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    # refreshed_at moves only when the text actually changed; checked_at moves on
    # every audit pass and orders the rotation.
    summary_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    summary_quality: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
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
