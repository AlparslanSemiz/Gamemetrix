from datetime import date, datetime
import re

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .integrations.source_registry import (
    CRITIC_SOURCES,
    PC_PLATFORM_KEYS,
    PRIMARY_SOURCES as PRIMARY_RATING_SOURCES,
    USER_RATING_SOURCES,
    applicable_for_game,
)
SOFTWARE_GENRE_TERMS = {
    "animation",
    "audio production",
    "design",
    "education",
    "game development",
    "photo editing",
    "software",
    "video production",
    "web publishing",
}
KNOWN_CONTENT_TYPE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\baseprite\b", "software"),
    (r"\bwallpaper engine\b", "utility"),
    (r"\blossless scaling\b", "utility"),
    (r"\bsoundpad\b", "utility"),
    (r"\bvoicemod\b", "utility"),
    (r"\bvtube studio\b", "software"),
    (r"\bfacerig\b", "software"),
    (r"\bblender\b", "software"),
    (r"\bkrita\b", "software"),
    (r"\bclip studio paint\b", "software"),
    (r"\bsubstance\b", "software"),
    (r"\bmarmoset toolbag\b", "software"),
    (r"\brpg maker\b", "software"),
    (r"\bvisual novel maker\b", "software"),
    (r"\bgame maker\b", "software"),
    (r"\bgamemaker\b", "software"),
    (r"\bappgamekit\b", "software"),
    (r"\bclickteam fusion\b", "software"),
    (r"\bconstruct\b", "software"),
    (r"\bgodot\b", "software"),
    (r"\bunreal engine\b", "software"),
    (r"\bgameguru\b", "software"),
    (r"\bleadwerks\b", "software"),
    (r"\bspriter\b", "software"),
    (r"\bgame character hub\b", "software"),
    (r"\btilesetter\b", "software"),
)


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    cover_url: Mapped[str] = mapped_column(String(500), nullable=False)
    release_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    release_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    metacritic_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ratings_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False, default="game")
    metrix_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
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
    playtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    award_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    award_nominations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    goty_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship("PriceSnapshot", back_populates="game", cascade="all, delete-orphan", lazy="select")

    @property
    def is_pc_applicable(self) -> bool:
        return any(p.lower() in PC_PLATFORM_KEYS for p in self.platforms)

    @property
    def applicable_primary_sources(self) -> frozenset[str]:
        return applicable_for_game(self.platforms)

    @property
    def applicable_sources(self) -> list[str]:
        return sorted(self.applicable_primary_sources)

    @property
    def applicable_source_count(self) -> int:
        return len(self.applicable_primary_sources)

    @property
    def live_primary_source_count(self) -> int:
        applicable = self.applicable_primary_sources
        return sum(
            1
            for score in self.source_scores
            if score.get("source") in applicable
            and score.get("status") == "live"
            and float(score.get("score", 0)) > 0
        )

    @property
    def confidence_level(self) -> str:
        applicable = self.applicable_primary_sources
        applicable_user = applicable & USER_RATING_SOURCES
        total_reviews = sum(
            int(s.get("review_count", 0))
            for s in self.source_scores
            if s.get("source") in applicable and s.get("status") == "live"
        )
        has_critic = any(
            s.get("source") in CRITIC_SOURCES
            and s.get("status") == "live"
            and float(s.get("score", 0)) > 0
            for s in self.source_scores
        )
        has_user = any(
            s.get("source") in applicable_user
            and s.get("status") == "live"
            and float(s.get("score", 0)) > 0
            for s in self.source_scores
        )
        if has_critic and has_user and total_reviews >= 500:
            return "Strong"
        if has_critic and has_user:
            return "Solid"
        if has_critic and total_reviews >= 50:
            return "Solid"
        if total_reviews >= 25000:
            return "Solid"
        if has_critic or has_user:
            return "Limited"
        return "Catalog"

    @property
    def score_profile(self) -> str:
        live_sources = {
            str(s.get("source"))
            for s in self.source_scores
            if s.get("status") == "live" and float(s.get("score", 0)) > 0
        }
        has_critic = bool(live_sources & CRITIC_SOURCES)
        has_user = bool(live_sources & USER_RATING_SOURCES)
        if has_critic and has_user:
            return "critic + user"
        if has_critic:
            return "critic-heavy"
        if has_user:
            return "user-heavy"
        return "sparse"

    @property
    def popularity_label(self) -> str | None:
        for s in self.source_scores:
            if s.get("source") not in {"Steam", "SteamSpy"}:
                continue
            count = int(s.get("review_count", 0))
            if count >= 100_000:
                return "Very High"
            if count >= 20_000:
                return "High"
            if count >= 5_000:
                return "Medium"
        return None


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


def infer_content_type(game: Game) -> str:
    text = " ".join(
        [
            game.title,
            game.slug,
            *(game.genres or []),
            *(game.platforms or []),
        ]
    ).lower()
    for pattern, content_type in KNOWN_CONTENT_TYPE_PATTERNS:
        if re.search(pattern, text):
            return content_type
    if "soundtrack" in text or re.search(r"\bost\b", text):
        return "soundtrack"
    if re.search(r"\b(demo|playtest|beta)\b", text):
        return "demo"
    if re.search(r"\b(dlc|downloadable content|season pass|expansion pass)\b", text):
        return "dlc"
    if re.search(r"\b(mod|sdk)\b", text):
        return "mod"
    if re.search(r"\b(utility|utilities|tool|tools)\b", text):
        return "utility"
    if any(term in text for term in SOFTWARE_GENRE_TERMS):
        return "software"
    return "game"
