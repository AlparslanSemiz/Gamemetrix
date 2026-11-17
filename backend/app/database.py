import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required. Use postgresql+psycopg://user:password@host:5432/database.")
if not DATABASE_URL.startswith("postgresql+psycopg://"):
    raise RuntimeError("DATABASE_URL must use postgresql+psycopg://.")

# Request engine: a bounded pool that fails fast (503 via main.py) instead of queueing
# callers for 30 s, and a statement timeout so one runaway catalog query cannot hold a
# connection (and the 224 MB database container) hostage.
REQUEST_STATEMENT_TIMEOUT_MS = 8000
# Background engine: full-catalog scans (SEO refresh, rating plan, completeness sweep)
# legitimately run for minutes, so they get their own small pool and a long timeout.
BACKGROUND_STATEMENT_TIMEOUT_MS = 15 * 60 * 1000


def _statement_timeout(milliseconds: int) -> dict[str, str]:
    return {"options": f"-c statement_timeout={milliseconds}"}


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=8,
    max_overflow=4,
    pool_timeout=5,
    pool_recycle=1800,
    connect_args=_statement_timeout(REQUEST_STATEMENT_TIMEOUT_MS),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

background_engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=2,
    pool_timeout=30,
    pool_recycle=1800,
    connect_args=_statement_timeout(BACKGROUND_STATEMENT_TIMEOUT_MS),
)
BackgroundSessionLocal = sessionmaker(bind=background_engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_long_db() -> Generator[Session, None, None]:
    """Session for admin endpoints that scan the whole catalog (long statement timeout)."""
    db = BackgroundSessionLocal()
    try:
        yield db
    finally:
        db.close()
