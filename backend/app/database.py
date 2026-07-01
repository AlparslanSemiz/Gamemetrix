import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv()

_ENV_DIR = Path(__file__).resolve().parents[1]

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./gamemetrix.dev.db",
)

_is_sqlite = DATABASE_URL.startswith("sqlite")
if DATABASE_URL.startswith("sqlite:///"):
    sqlite_path = DATABASE_URL.removeprefix("sqlite:///")
    if sqlite_path and sqlite_path != ":memory:" and not os.path.isabs(sqlite_path):
        DATABASE_URL = f"sqlite:///{(_ENV_DIR / sqlite_path).resolve().as_posix()}"

_engine_kwargs: dict = {"pool_pre_ping": True}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)

if _is_sqlite:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")   # concurrent reads during writes
        cursor.execute("PRAGMA synchronous=NORMAL") # safe but faster than FULL
        cursor.execute("PRAGMA cache_size=-32000")  # 32 MB page cache
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
