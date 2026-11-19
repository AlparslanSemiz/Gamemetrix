"""Audit stored Steam app ids against appdetails (the logic behind verify_steam_ids).

Each game with a `steam_app_id` is checked once: appdetails must be a `game` whose
name/qualifiers/year agree with the row. Verified ids get a stamp; refuted ids are
cleared together with the scores and prices that were fetched from the wrong app,
and the game lands on the admin review queue. Outages never count as refutation.
"""

import asyncio
import re
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import Select, delete, or_, select
from sqlalchemy.orm import Session

from ..integrations.steam.client import AppdetailsOutcome, fetch_app_outcome
from ..integrations.steam.identity import SteamIdentity, identity_from_appdetails
from ..integrations.steam.parsing import parse_release_date
from ..integrations.sync import calculate_metrix_score, compute_rank_fields
from ..models import Game, PriceSnapshot
from .keyset_scan import SCAN_BATCH_SIZE, keyset_batches
from .steam_identity import (
    apply_steam_product_type,
    claim_steam_app_id,
    clear_steam_app_id,
    queue_steam_review,
)

# Steam's store API allows roughly 200 requests per 5 minutes.
DEFAULT_DELAY_SECONDS = 1.6
DEFAULT_REVERIFY_DAYS = 90
_STEAM_DERIVED_SOURCES = frozenset({"Steam", "SteamSpy"})

Fetcher = Callable[[int], Awaitable[AppdetailsOutcome]]


@dataclass
class AuditFinding:
    game_id: int
    slug: str
    title: str
    steam_app_id: int
    verdict: str  # verified | reclassified | doubtful | mismatch | removed | unknown
    reason: str
    steam_name: str | None = None


@dataclass
class AuditReport:
    apply: bool
    checked: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    findings: list[AuditFinding] = field(default_factory=list)
    stopped_early: str | None = None
    last_id: int = 0

    def add(self, finding: AuditFinding) -> None:
        self.checked += 1
        self.last_id = finding.game_id
        self.counts[finding.verdict] = self.counts.get(finding.verdict, 0) + 1
        if finding.verdict != "verified":
            self.findings.append(finding)


_CANDIDATE_COLUMNS = (Game.id, Game.slug, Game.title, Game.release_year, Game.steam_app_id)


def _candidate_query(
    *,
    reverify_days: int | None,
    game_ids: Collection[int] | None = None,
) -> Select[Any]:
    """Only the columns `judge` and the report need: no JSON blobs per scanned row."""
    stmt = select(*_CANDIDATE_COLUMNS).where(Game.steam_app_id.is_not(None))
    if game_ids is not None:
        stmt = stmt.where(Game.id.in_(list(game_ids)))
    if reverify_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=reverify_days)
        stmt = stmt.where(
            or_(Game.steam_app_id_verified_at.is_(None), Game.steam_app_id_verified_at < cutoff)
        )
    return stmt


_EXPLICIT_YEAR = re.compile(r"\((?:19|20)\d{2}\)")


def judge(game: Any, outcome: AppdetailsOutcome) -> tuple[str, str, SteamIdentity | None]:
    if outcome.status == "error":
        return "unknown", "appdetails unavailable (outage or rate limit)", None
    if outcome.status == "removed":
        return "removed", "Steam has no appdetails for this id", None
    data = outcome.data or {}
    release = parse_release_date((data.get("release_date") or {}).get("date"))
    identity = identity_from_appdetails(game.title, game.release_year, data, release)
    if identity.ok:
        return "verified", "ok", identity
    if identity.name_matches and identity.steam_type and identity.steam_type != "game":
        return "reclassified", f"same product, Steam type {identity.steam_type}", identity
    explicit_year = _EXPLICIT_YEAR.search(game.title or "") or _EXPLICIT_YEAR.search(str(data.get("name") or ""))
    if identity.name_matches and identity.reason == "year_mismatch" and not explicit_year:
        # Same name, years apart: a late PC port (The Last of Us Part I, POSTAL 2) or a
        # same-name reboot (Doom 1993/2016). Too close to call by data alone, and
        # clearing a correct id loses its scores: keep it unverified and ask a human.
        return "doubtful", identity.reason, identity
    return "mismatch", identity.reason, identity


def purge_wrong_app_data(db: Session, game: Game) -> None:
    """Drop Steam-derived scores and prices; they described another product."""
    game.source_scores = [
        row for row in game.source_scores or []
        if not (isinstance(row, dict) and row.get("source") in _STEAM_DERIVED_SOURCES)
    ]
    game.metrix_score = calculate_metrix_score(game.source_scores)
    game.rank_score, game.is_rankable, _ = compute_rank_fields(game)
    game.ratings_refreshed_at = None
    game.prices_refreshed_at = None
    db.execute(delete(PriceSnapshot).where(PriceSnapshot.game_id == game.id, PriceSnapshot.source == "Steam"))


def _apply(db: Session, game: Game, verdict: str, reason: str, identity: SteamIdentity | None) -> None:
    app_id = int(game.steam_app_id or 0)
    if verdict == "verified":
        claim_steam_app_id(db, game, app_id, verified=True)
    elif verdict == "reclassified" and identity is not None:
        claim_steam_app_id(db, game, app_id, verified=True)
        apply_steam_product_type(game, identity)
    elif verdict == "mismatch":
        clear_steam_app_id(db, game)
        purge_wrong_app_data(db, game)
        queue_steam_review(db, game, f"Steam app {app_id} refuted ({reason}); id cleared")
    elif verdict == "doubtful":
        queue_steam_review(db, game, f"Steam app {app_id} has the same name but another year ({reason}); id kept, please check")
    elif verdict == "removed":
        queue_steam_review(db, game, f"Steam app {app_id} returns no appdetails; id kept, please check")
    db.add(game)


_Pending = tuple[int, int, str, str, SteamIdentity | None]  # game id, app id, verdict, reason, identity


def _write_verdicts(db: Session, pending: list[_Pending]) -> None:
    """One short write transaction for a burst of verdicts (apply mode only)."""
    for game_id, app_id, verdict, reason, identity in pending:
        game = db.get(Game, game_id)
        if game is None or game.steam_app_id != app_id:
            continue  # merged, deleted or re-pointed since it was read
        _apply(db, game, verdict, reason, identity)
    db.commit()
    pending.clear()


async def audit_steam_ids(
    db: Session,
    *,
    apply: bool = False,
    limit: int | None = None,
    after_id: int = 0,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    reverify_days: int | None = DEFAULT_REVERIFY_DAYS,
    fetcher: Fetcher | None = None,
    commit_every: int = 25,
    game_ids: Collection[int] | None = None,
    batch_size: int = SCAN_BATCH_SIZE,
) -> AuditReport:
    """Read candidates in keyset batches, fetch appdetails with no transaction open,
    then write verdicts in short transactions of `commit_every` (apply mode only)."""
    report = AuditReport(apply=apply)
    owned: httpx.AsyncClient | None = None
    if fetcher is None:
        owned = httpx.AsyncClient()
        client = owned

        async def fetcher(app_id: int) -> AppdetailsOutcome:  # noqa: F811
            return await fetch_app_outcome(app_id, client)

    stmt = _candidate_query(reverify_days=reverify_days, game_ids=game_ids)
    pending: list[_Pending] = []
    consecutive_errors = 0
    fetched = 0
    try:
        for batch in keyset_batches(db, stmt, Game.id, batch_size=batch_size, after=after_id, limit=limit):
            for row in batch:
                if fetched and delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)
                app_id = int(row.steam_app_id or 0)
                outcome = await fetcher(app_id)
                fetched += 1
                verdict, reason, identity = judge(row, outcome)
                report.add(AuditFinding(
                    row.id, row.slug, row.title, app_id, verdict, reason,
                    steam_name=str((outcome.data or {}).get("name") or "") or None,
                ))
                consecutive_errors = consecutive_errors + 1 if verdict == "unknown" else 0
                if consecutive_errors >= 5:
                    report.stopped_early = "5 consecutive appdetails errors (rate limit?); stopped"
                    break
                if apply and verdict != "unknown":
                    pending.append((row.id, app_id, verdict, reason, identity))
                    if len(pending) >= commit_every:
                        _write_verdicts(db, pending)
            if report.stopped_early:
                break
        if apply and pending:
            _write_verdicts(db, pending)
        if not apply:
            db.rollback()
    finally:
        if owned is not None:
            await owned.aclose()
    return report
