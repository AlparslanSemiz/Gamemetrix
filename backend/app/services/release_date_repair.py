"""Repair 1970-01-01 placeholders and original-vs-remaster date mix-ups from appdetails.

Only trusts a Steam date when appdetails is the same product (identity check), so a
wrong app id can never write a wrong date. Rules, per game with a Steam id:

  unknown   our year is the 1970 placeholder        -> take Steam's date
  earlier   Steam's year is 2+ years before ours,    -> take Steam's date (our date is
            title is not a remaster/remake             a later re-release of the original)
  conflict  anything else that differs               -> reported, never written (a later
            Steam date is usually a PC port, which is not an error)
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..integrations.steam.client import AppdetailsOutcome, fetch_app_outcome
from ..integrations.steam.identity import identity_from_appdetails
from ..integrations.steam.parsing import parse_release_date
from ..models import Game
from .keyset_scan import SCAN_BATCH_SIZE, keyset_batches

UNKNOWN_YEAR = 1970
_REMASTER_RE = ("remaster", "remake", "definitive", "legendary edition", "anniversary", "hd collection")

Fetcher = Callable[[int], Awaitable[AppdetailsOutcome]]


@dataclass
class DateChange:
    game_id: int
    slug: str
    kind: str  # unknown | earlier | conflict | identity_mismatch | no_steam_date
    old: date
    new: date | None


@dataclass
class DateRepairReport:
    apply: bool
    checked: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    changes: list[DateChange] = field(default_factory=list)


class _DatedTitle(Protocol):
    title: str
    release_year: int


def classify(game: _DatedTitle, steam_date: date) -> str | None:
    """None when the dates already agree."""
    if game.release_year <= UNKNOWN_YEAR:
        return "unknown"
    if steam_date.year == game.release_year:
        return None
    is_remaster = any(marker in game.title.lower() for marker in _REMASTER_RE)
    if steam_date.year <= game.release_year - 2 and not is_remaster:
        return "earlier"
    return "conflict"


# Only what classification and the report read: no JSON blobs per scanned row.
_CANDIDATE_COLUMNS = (Game.id, Game.slug, Game.title, Game.release_year, Game.release_date, Game.steam_app_id)


def _write_dates(db: Session, pending: list[tuple[int, date]]) -> None:
    """One short write transaction for a burst of fixes (apply mode only)."""
    for game_id, steam_date in pending:
        game = db.get(Game, game_id)
        if game is None:
            continue
        game.release_date = steam_date
        game.release_year = steam_date.year
        if game.official_release_date is None:
            game.official_release_date = steam_date
        db.add(game)
    db.commit()
    pending.clear()


async def repair_release_dates(
    db: Session,
    *,
    apply: bool = False,
    scan_all: bool = False,
    limit: int | None = None,
    delay_seconds: float = 1.6,
    fetcher: Fetcher | None = None,
    commit_every: int = 25,
    batch_size: int = SCAN_BATCH_SIZE,
) -> DateRepairReport:
    """Read candidates in keyset batches, fetch appdetails with no transaction open,
    then write fixes in short transactions of `commit_every` (apply mode only)."""
    report = DateRepairReport(apply=apply)
    stmt = select(*_CANDIDATE_COLUMNS).where(Game.steam_app_id.is_not(None))
    if not scan_all:
        stmt = stmt.where(Game.release_year <= UNKNOWN_YEAR)

    owned: httpx.AsyncClient | None = None
    if fetcher is None:
        owned = httpx.AsyncClient()
        client = owned

        async def fetcher(app_id: int) -> AppdetailsOutcome:  # noqa: F811
            return await fetch_app_outcome(app_id, client)

    pending: list[tuple[int, date]] = []
    try:
        for batch in keyset_batches(db, stmt, Game.id, batch_size=batch_size, limit=limit):
            for game in batch:
                if report.checked and delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)
                outcome = await fetcher(int(game.steam_app_id or 0))
                report.checked += 1
                if outcome.status != "ok":
                    continue
                data = outcome.data or {}
                steam_date = parse_release_date((data.get("release_date") or {}).get("date"))
                if steam_date is None:
                    _record(report, game, "no_steam_date", None)
                    continue
                if not identity_from_appdetails(game.title, game.release_year, data, steam_date).ok:
                    _record(report, game, "identity_mismatch", steam_date)
                    continue
                kind = classify(game, steam_date)
                if kind is None:
                    continue
                _record(report, game, kind, steam_date)
                if apply and kind in {"unknown", "earlier"}:
                    pending.append((game.id, steam_date))
                    if len(pending) >= commit_every:
                        _write_dates(db, pending)
        if apply and pending:
            _write_dates(db, pending)
        if not apply:
            db.rollback()
    finally:
        if owned is not None:
            await owned.aclose()
    return report


def _record(report: DateRepairReport, game: Any, kind: str, new: date | None) -> None:
    report.counts[kind] = report.counts.get(kind, 0) + 1
    report.changes.append(DateChange(game.id, game.slug, kind, game.release_date, new))
