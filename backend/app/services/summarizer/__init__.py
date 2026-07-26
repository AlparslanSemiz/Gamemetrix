"""AI-audited game descriptions.

Rotates the whole catalog so every description is periodically re-checked for
junk, promotional text, broken encoding, wrong language, duplication and excess
length — repaired mechanically where that is enough, judged and rewritten by
AI where it is not — and derives the compact display blurb from the result.

Public API:
  describe_issues(text)                      -> list[str]
  sanitize_description(text)                 -> str
  audit_description(title, text, issues)     -> Awaitable[DescriptionVerdict | None]
  shorten_summary(title, summary)            -> Awaitable[str]
  needs_short_summary(game)                  -> bool
  refresh_summary_batch(db, limit, ai_limit) -> Awaitable[dict[str, int]]
"""

from .ai import DescriptionVerdict, audit_description, parse_audit_answer, shorten_summary
from .batch import needs_short_summary, refresh_summary_batch
from .issues import describe_issues, needs_ai_review, sanitize_description

__all__ = [
    "DescriptionVerdict",
    "audit_description",
    "describe_issues",
    "needs_ai_review",
    "needs_short_summary",
    "parse_audit_answer",
    "refresh_summary_batch",
    "sanitize_description",
    "shorten_summary",
]
