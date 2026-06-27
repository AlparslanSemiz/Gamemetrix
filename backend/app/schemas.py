from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


GameSort = Literal[
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


class GameRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    summary: str
    cover_url: str
    release_date: date
    release_year: int
    metacritic_score: int | None = None
    image_url: str | None = None
    ratings_refreshed_at: datetime | None = None
    content_type: str = "game"
    live_primary_source_count: int = 0
    applicable_source_count: int = 4
    applicable_sources: list[str] = []
    confidence_level: str = "Limited"
    score_profile: str = "sparse"
    popularity_label: str | None = None
    metrix_score: float
    critic_score: float
    user_score: float
    genres: list[str]
    platforms: list[str]
    source_scores: list[SourceScore]
    developer: str | None = None
    publisher: str | None = None
    playtime_minutes: int = 0
    award_count: int = 0
    award_nominations: int = 0
    goty_year: int | None = None


class GameListResponse(BaseModel):
    games: list[GameRead]
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
