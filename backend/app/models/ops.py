"""Operational tables: provider budgets, admin audit trail, data-fill runs."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


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
    # Token ceilings apply to LLM providers, where the request count runs out
    # long after the token allowance does. Zero means "this source has no token
    # limit" and only request_count is enforced.
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    token_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
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
    target_total: Mapped[int] = mapped_column(Integer, nullable=False, default=50000)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobRun(Base):
    """Heartbeat for one periodic background loop: its most recent cycle only.

    One row per job (upserted every cycle) — the admin panel reads this to show
    when each loop last ran, when it is next due, and what that run fetched.
    """

    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job: Mapped[str] = mapped_column(String(48), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CatalogQualityReview(Base):
    """Persistent Groq verdict for one catalog row and the signals that triggered it."""

    __tablename__ = "catalog_quality_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    signals: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class CatalogSyncState(Base):
    """Durable cursor for a resumable upstream catalog scan."""

    __tablename__ = "catalog_sync_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    cursor: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
