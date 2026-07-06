from datetime import date, datetime
import re

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .integrations.source_registry import (
    CRITIC_SOURCES,
    PC_PLATFORM_KEYS,
    PRIMARY_SOURCES as PRIMARY_RATING_SOURCES,
    RATING_SOURCES,
    USER_RATING_SOURCES,
    applicable_for_game,
)
# Confidence level thresholds
_STRONG_MIN_REVIEWS = 500
_SOLID_MIN_REVIEWS = 100
_SOLID_CRITIC_MIN_REVIEWS = 50
_LIMITED_MIN_REVIEWS = 1

# Popularity label thresholds (total review count)
_POPULARITY_PHENOMENON = 500_000
_POPULARITY_VERY_HIGH = 100_000
_POPULARITY_HIGH = 25_000
_POPULARITY_MEDIUM = 5_000
_POPULARITY_LOW = 500

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
    summary_short: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    content_type: Mapped[str] = mapped_column(String(40), nullable=False, default="game")
    metrix_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    rank_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, index=True)
    is_rankable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
    awards: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    screenshots: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    system_requirements: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    dlcs: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    similar_games: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    proton_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    proton_score: Mapped[float | None] = mapped_column(Float, nullable=True)

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

        live_rating_entries = [
            s for s in self.source_scores
            if s.get("status") == "live"
            and float(s.get("score", 0)) > 0
            and str(s.get("source")) in RATING_SOURCES
        ]
        live_sources: set[str] = {str(s.get("source")) for s in live_rating_entries}
        live_primary = live_sources & applicable
        live_critic = live_primary & CRITIC_SOURCES
        live_user = live_primary & applicable_user
        total_reviews = sum(
            int(s.get("review_count", 0))
            for s in live_rating_entries
        )

        if (
            len(live_primary) >= min(3, len(applicable))
            and live_critic
            and live_user
            and total_reviews >= _STRONG_MIN_REVIEWS
        ):
            return "Strong"
        if live_critic and live_user and len(live_primary) >= 2 and total_reviews >= _SOLID_MIN_REVIEWS:
            return "Solid"
        if len(live_critic) >= 2 and total_reviews >= _SOLID_CRITIC_MIN_REVIEWS:
            return "Solid"
        if len(live_primary) >= 3:
            return "Solid"
        if live_primary and total_reviews >= _LIMITED_MIN_REVIEWS:
            return "Limited"
        if "RAWG" in live_sources:
            return "Limited"
        return "Catalog"

    @property
    def data_strength(self) -> str:
        _map = {"Strong": "DATA_STRONG", "Solid": "DATA_SOLID", "Limited": "DATA_LIMITED", "Catalog": "CATALOG_ONLY"}
        return _map.get(self.confidence_level, "CATALOG_ONLY")

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
        live_sources = {
            str(s.get("source"))
            for s in self.source_scores
            if s.get("status") == "live"
            and float(s.get("score", 0)) > 0
            and str(s.get("source")) in RATING_SOURCES
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
        count = sum(
            int(s.get("review_count", 0))
            for s in self.source_scores
            if s.get("status") == "live"
            and str(s.get("source")) in RATING_SOURCES
        )
        if count >= _POPULARITY_PHENOMENON:
            return "Phenomenon"
        if count >= _POPULARITY_VERY_HIGH:
            return "Very High"
        if count >= _POPULARITY_HIGH:
            return "High"
        if count >= _POPULARITY_MEDIUM:
            return "Medium"
        if count >= _POPULARITY_LOW:
            return "Niche"
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


class VisitEvent(Base):
    """Privacy-preserving page-view event for admin traffic analytics."""

    __tablename__ = "visit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    visitor_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    referrer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    screen_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    screen_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
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


_DLC_TITLE_RE = re.compile(
    r"""
    \b(?:
        dlc                             |
        downloadable\s+content          |
        season\s+pass                   |
        expansion\s+pass                |
        booster\s+pack                  |
        character\s+pack                |
        costume\s+pack                  |
        skin\s+pack                     |
        map\s+pack                      |
        weapon\s+pack                   |
        armor\s+pack                    |
        mission\s+pack                  |
        level\s+pack                    |
        adventure\s+pack                |
        content\s+pack                  |
        story\s+pack                    |
        add-?on\s+pack
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Title suffixes that indicate a sub-episode or DLC chapter
_EPISODE_SUFFIX_RE = re.compile(
    r"[\s\-–—]+(?:episode|chapter|part)\s+\d",
    re.IGNORECASE,
)

# The subtitle part (after " – " or " - ") must contain one of these keywords
# to be classified as a DLC via the parent-based heuristic.
# We deliberately require an explicit DLC-like keyword in the subtitle to avoid
# false-positives from games that just have a subtitle (e.g. "Eco - Global Survival Game").
_DLC_SUBTITLE_RE = re.compile(
    r"""
    \b(?:
        dlc                 |
        expansion           |
        add-?on             |
        episode\s+\d        |
        chapter\s+\d        |
        part\s+\d           |
        season\s+\d         |
        prelude             |
        prologue            |
        echoes              |     # Outer Wilds - Echoes of the Eye
        blood\s+dragon      |     # Far Cry 3 - Blood Dragon
        cindered\s+shadows  |     # Fire Emblem
        aiko.s\s+choice     |     # Shadow Tactics
        separate\s+ways     |     # RE4
        blood\s+and\s+wine  |     # Witcher 3
        hearts\s+of\s+stone |     # Witcher 3
        clone\s+carnage     |     # Destroy All Humans
        the\s+penal\s+zone  |     # Sam & Max
        iron\s+from\s+ice   |     # Game of Thrones
        zer0\s+sum          |     # Tales from the Borderlands
        toy\s+master        |     # Killing Floor
        wildfire            |     # Jagged Alliance 2
        rise\s+of\s+clans   |     # Hard Truck
        dark\s+crusade      |     # Dawn of War
        soulstorm           |     # Dawn of War
        winter\s+assault    |     # Dawn of War
        yuri.s\s+revenge    |     # C&C Red Alert 2
        uprising            |     # C&C Red Alert 3
        zero\s+hour               # C&C Generals
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# RAWG game_type values that indicate DLC/expansion
_RAWG_DLC_TYPES = frozenset({"dlc", "expansion", "addon", "update"})


def infer_content_type(game: Game, rawg_game_type: str | None = None) -> str:
    # RAWG explicitly tells us the type — trust it
    if rawg_game_type and rawg_game_type.lower() in _RAWG_DLC_TYPES:
        return "dlc"

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
    if re.search(r"\b(demo|playtest)\b", text) or re.search(r"\bbeta\b", game.title, re.IGNORECASE):
        return "demo"
    if _DLC_TITLE_RE.search(game.title):
        return "dlc"
    if re.search(r"\b(dlc|downloadable content|season pass|expansion pass)\b", text):
        return "dlc"
    if _EPISODE_SUFFIX_RE.search(game.title):
        return "dlc"
    if re.search(r"\b(mod|sdk)\b", text):
        return "mod"
    if re.search(r"\b(utility|utilities|tool|tools)\b", text):
        return "utility"
    if any(term in text for term in SOFTWARE_GENRE_TERMS):
        return "software"
    return "game"


def infer_content_type_with_parent(game: Game, parent_titles: frozenset[str]) -> str:
    """
    Extended classification that checks whether this game is a DLC/expansion of
    a parent game already in the catalog.

    Requires:
      1. Title matches "Parent Title – Subtitle" or "Parent Title - Subtitle"
      2. The parent title exists in the catalog
      3. The subtitle contains a recognized DLC/expansion keyword

    parent_titles: frozenset of all game titles currently in the DB (lowercase).
    """
    base_type = infer_content_type(game)
    if base_type != "game":
        return base_type

    title = game.title.strip()
    for sep in (" – ", " — ", " - "):
        if sep not in title:
            continue
        idx = title.index(sep)
        parent_candidate = title[:idx].strip()
        subtitle = title[idx + len(sep):].strip()
        if not subtitle or not parent_candidate:
            continue
        # Parent must exist in catalog
        if parent_candidate.lower() not in parent_titles:
            continue
        # Subtitle must have an explicit DLC/expansion keyword
        if _DLC_SUBTITLE_RE.search(subtitle):
            return "dlc"
    return "game"
