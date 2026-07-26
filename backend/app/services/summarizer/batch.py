"""Rotating description audit: sanitize mechanically, escalate the rest to AI.

Games are visited oldest-checked first, so the whole catalog cycles through the
audit and games come back around as their descriptions change. Each pass:

  1. deterministic issue detection (free)
  2. mechanical repair — markup, encoding, promo, boilerplate, duplication (free)
  3. AI audit for what is left, unresolved problems before never-audited rows
  4. regeneration of the compact display blurb when the text moved

Step 3 is capped per batch: AI is one shared logical-call budget across summaries,
catalog quality, endless detection and reranking.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, noload

from ...models import Game
from ..metadata import UNUSABLE_SUMMARY_QUALITY
from .ai import REJECTED_VERDICT, audit_description, extract_short_summary, shorten_summary
from .issues import (
    MIN_DESCRIPTION_CHARS,
    describe_issues,
    is_unfixable,
    needs_ai_review,
    sanitize_description,
)

log = logging.getLogger(__name__)

OK_SUMMARY_QUALITY = "ok"
CLEANED_SUMMARY_QUALITY = "cleaned"

_MIN_SHORT_SOURCE_CHARS = 200


@dataclass(eq=False)
class _Candidate:
    """One game's description state after the free deterministic passes."""

    game: Game
    text: str
    issues: list[str] = field(default_factory=list)
    changed: bool = False


def needs_short_summary(game: Game) -> bool:
    if game.summary_short:
        return False
    return len(game.summary) >= _MIN_SHORT_SOURCE_CHARS


async def refresh_summary_batch(db: Session, limit: int, ai_limit: int) -> dict[str, int]:
    """Audit the next `limit` descriptions, spending at most `ai_limit` AI calls."""
    games = list(
        db.scalars(
            select(Game)
            .where(Game.content_type == "game")
            .options(noload(Game.price_snapshots))
            .order_by(Game.summary_checked_at.asc().nulls_first(), Game.id.asc())
            .limit(limit)
        ).all()
    )
    counts = _empty_counts()
    now = datetime.now(UTC)
    budget = _Budget(ai_limit)

    candidates = [_deterministic_pass(game, counts) for game in games]
    for candidate in _ai_order(candidates):
        if not budget.available:
            break
        await _ai_pass(candidate, counts, budget)

    for candidate in candidates:
        _apply_text(candidate, now)
        if needs_short_summary(candidate.game):
            candidate.game.summary_short = await _short_summary(candidate.game, budget)
            counts["shortened"] += 1
        candidate.game.summary_checked_at = now
        db.add(candidate.game)
        counts["processed"] += 1

    db.commit()
    return counts


class _Budget:
    """Remaining logical AI calls this batch may spend."""

    def __init__(self, limit: int) -> None:
        self.remaining = max(0, limit)

    @property
    def available(self) -> bool:
        return self.remaining > 0

    def spend(self) -> None:
        self.remaining -= 1

    def exhaust(self) -> None:
        self.remaining = 0


def _deterministic_pass(game: Game, counts: dict[str, int]) -> _Candidate:
    issues = describe_issues(game.summary)
    if is_unfixable(issues):
        game.summary_quality = UNUSABLE_SUMMARY_QUALITY
        counts["unusable"] += 1
        return _Candidate(game=game, text=game.summary, issues=issues)
    if not issues:
        return _Candidate(game=game, text=game.summary)

    sanitized = sanitize_description(game.summary)
    if not _is_safe_replacement(game.summary, sanitized):
        return _Candidate(game=game, text=game.summary, issues=issues)

    counts["sanitized"] += 1
    return _Candidate(
        game=game,
        text=sanitized,
        issues=describe_issues(sanitized),
        changed=True,
    )


def _is_safe_replacement(original: str, sanitized: str) -> bool:
    """Reject a mechanical clean-up that gutted the description.

    Stripping every promotional or boilerplate sentence can leave a fragment
    with less about the game than the messy original. In that case the original
    is the better input for the AI pass.
    """
    if not sanitized or sanitized == original:
        return False
    if is_unfixable(describe_issues(sanitized)):
        return False
    return len(sanitized) >= MIN_DESCRIPTION_CHARS or len(sanitized) >= len(original)


def _ai_order(candidates: list[_Candidate]) -> list[_Candidate]:
    """Rows with unresolved issues first, then rows AI has never seen."""
    flagged: list[_Candidate] = []
    unverified: list[_Candidate] = []
    for candidate in candidates:
        if is_unfixable(candidate.issues):
            continue
        if needs_ai_review(candidate.issues):
            flagged.append(candidate)
        elif candidate.game.summary_quality is None:
            unverified.append(candidate)
    return [*flagged, *unverified]


async def _ai_pass(candidate: _Candidate, counts: dict[str, int], budget: _Budget) -> None:
    game = candidate.game
    budget.spend()
    verdict = await audit_description(game.title, candidate.text, candidate.issues)
    if verdict is None:
        # No answer at all: daily budget spent or the provider is down. Further
        # calls in this batch would only repeat the same outcome.
        counts["unavailable"] += 1
        budget.exhaust()
        return

    counts["ai_checked"] += 1
    if verdict.verdict == REJECTED_VERDICT:
        counts["rejected"] += 1
        return
    if verdict.verdict == "UNUSABLE":
        game.summary_quality = UNUSABLE_SUMMARY_QUALITY
        counts["unusable"] += 1
        return
    if verdict.verdict == "CLEANED":
        candidate.text = verdict.summary
        candidate.changed = True
        game.summary_quality = CLEANED_SUMMARY_QUALITY
        counts["cleaned"] += 1
        return
    game.summary_quality = CLEANED_SUMMARY_QUALITY if candidate.changed else OK_SUMMARY_QUALITY
    counts["ok"] += 1


async def _short_summary(game: Game, budget: _Budget) -> str:
    """AI blurb while budget lasts, otherwise a sentence-boundary extract.

    Never skipped: the extract is good enough that leaving the field empty for a
    whole rotation would be the worse outcome, and it keeps the job working with
    no configured AI provider at all.
    """
    if not budget.available:
        return extract_short_summary(game.summary)
    budget.spend()
    return await shorten_summary(game.title, game.summary)


def _apply_text(candidate: _Candidate, now: datetime) -> None:
    """Persist a changed description and invalidate its display blurb."""
    game = candidate.game
    if not candidate.changed or candidate.text == game.summary:
        return
    game.summary = candidate.text
    game.summary_short = None
    game.summary_refreshed_at = now
    if game.summary_quality is None:
        game.summary_quality = CLEANED_SUMMARY_QUALITY


def _empty_counts() -> dict[str, int]:
    return {
        "processed": 0,
        "sanitized": 0,
        "ai_checked": 0,
        "ok": 0,
        "cleaned": 0,
        "unusable": 0,
        "rejected": 0,
        "shortened": 0,
        "unavailable": 0,
    }
