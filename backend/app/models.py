from datetime import date

from sqlalchemy import Date, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    cover_url: Mapped[str] = mapped_column(String(500), nullable=False)
    release_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    release_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
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
