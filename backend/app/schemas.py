from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


GameSort = Literal[
    "rank_score",
    "metrix_score",
    "release_year",
    "title",
    "critic_score",
    "user_score",
    "metacritic_score",
    "opencritic_score",
    "steam_score",
    "review_count",
]
SortDirection = Literal["asc", "desc"]


class SourceScore(BaseModel):
    source: str
    score: float
    scale: int
    status: str = "mock"
    detail: str | None = None
    refreshed_at: str | None = None
    review_count: int = 0


class PriceSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    store: str
    platform: str | None = None
    region: str = "US"
    currency: str = "USD"
    list_price: float | None = None
    sale_price: float | None = None
    discount_percent: int | None = None
    historical_low: float | None = None
    historical_low_date: date | None = None
    sale_end_date: datetime | None = None
    is_free: bool = False
    is_subscription_included: bool = False
    subscription_service: str | None = None
    url: str | None = None
    fetched_at: datetime


class GameRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    summary: str
    summary_short: str | None = None
    cover_url: str
    release_date: date
    release_year: int
    early_access_date: date | None = None
    official_release_date: date | None = None
    metacritic_score: int | None = None
    image_url: str | None = None
    website_url: str | None = None
    ratings_refreshed_at: datetime | None = None
    metadata_refreshed_at: datetime | None = None
    content_type: str = "game"
    live_primary_source_count: int = 0
    applicable_source_count: int = 4
    applicable_sources: list[str] = []
    confidence_level: str = "Limited"
    data_strength: str = "CATALOG_ONLY"
    score_profile: str = "sparse"
    popularity_label: str | None = None
    metrix_score: float
    rank_score: float = 0.0
    is_rankable: bool = False
    rank_exclusion_reason: str | None = None
    critic_score: float
    user_score: float
    genres: list[str]
    platforms: list[str]
    source_scores: list[SourceScore]
    developer: str | None = None
    publisher: str | None = None
    playtime_minutes: int = 0
    hltb_id: int | None = None
    hltb_url: str | None = None
    hltb_main_story_minutes: int = 0
    hltb_main_extra_minutes: int = 0
    hltb_completionist_minutes: int = 0
    hltb_all_styles_minutes: int = 0
    hltb_refreshed_at: datetime | None = None
    proton_tier: str | None = None
    proton_score: float | None = None
    award_count: int = 0
    award_nominations: int = 0
    goty_year: int | None = None
    awards: list[str] = []
    screenshots: list[str] = []
    system_requirements: list[dict] = []
    dlcs: list[dict] = []
    similar_games: list[dict] = []
    price_snapshots: list[PriceSnapshotRead] = []


class GameListItem(BaseModel):
    """Lightweight game row for the list endpoint; prices are loaded only for deal views."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    summary: str
    summary_short: str | None = None
    cover_url: str
    release_date: date
    release_year: int
    early_access_date: date | None = None
    official_release_date: date | None = None
    metacritic_score: int | None = None
    image_url: str | None = None
    website_url: str | None = None
    ratings_refreshed_at: datetime | None = None
    metadata_refreshed_at: datetime | None = None
    content_type: str = "game"
    live_primary_source_count: int = 0
    applicable_source_count: int = 4
    applicable_sources: list[str] = []
    confidence_level: str = "Limited"
    data_strength: str = "CATALOG_ONLY"
    score_profile: str = "sparse"
    popularity_label: str | None = None
    metrix_score: float
    rank_score: float = 0.0
    is_rankable: bool = False
    rank_exclusion_reason: str | None = None
    critic_score: float
    user_score: float
    genres: list[str]
    platforms: list[str]
    source_scores: list[SourceScore]
    developer: str | None = None
    publisher: str | None = None
    playtime_minutes: int = 0
    hltb_id: int | None = None
    hltb_url: str | None = None
    hltb_main_story_minutes: int = 0
    hltb_main_extra_minutes: int = 0
    hltb_completionist_minutes: int = 0
    hltb_all_styles_minutes: int = 0
    hltb_refreshed_at: datetime | None = None
    proton_tier: str | None = None
    proton_score: float | None = None
    award_count: int = 0
    award_nominations: int = 0
    goty_year: int | None = None
    awards: list[str] = []
    screenshots: list[str] = []
    system_requirements: list[dict] = []
    dlcs: list[dict] = []
    similar_games: list[dict] = []
    price_snapshots: list[PriceSnapshotRead] = []


class GameListResponse(BaseModel):
    games: list[GameListItem]
    total: int


class SeriesGameItem(BaseModel):
    """Minimal payload for the franchise strip — keep this lean, it renders as small tiles."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    cover_url: str
    release_year: int
    metrix_score: float


class SeriesResponse(BaseModel):
    series_key: str
    games: list[SeriesGameItem]
    total: int


class FacetsResponse(BaseModel):
    genres: list[str]
    years: list[int]
    platforms: list[str]


class ProviderStatus(BaseModel):
    source: str
    status: str
    detail: str


class ImportResponse(BaseModel):
    imported: int
    skipped: int


class MultiImportResponse(BaseModel):
    imported: int
    skipped: int
    sources: dict[str, ImportResponse]


class ScoreWeightsResponse(BaseModel):
    weights: dict[str, float]


class ScoreWeightsUpdate(BaseModel):
    weights: dict[str, float]


class RecalculateResponse(BaseModel):
    recalculated: int


class RatingsEnrichResponse(BaseModel):
    enriched: int
    skipped: int


class MetadataFixResponse(BaseModel):
    fixed: int
    skipped: int


class TrailerResponse(BaseModel):
    video_id: str | None
    watch_url: str | None
