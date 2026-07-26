"""AI prompts, strict parsing and output validation for descriptions.

The model's answer is never written straight to the database. Every returned
description is clamped to the length cap, re-run through the deterministic issue
checks, and — for text that was already English — required to share vocabulary
with the source, so a confidently invented description is rejected rather than
published.

Public API:
  audit_description(title, text, issues) -> Awaitable[DescriptionVerdict | None]
  shorten_summary(title, summary)        -> Awaitable[str]
  extract_short_summary(summary)         -> str
  parse_audit_answer(answer)             -> DescriptionVerdict | None
"""

import json
import logging
from dataclasses import dataclass

from ...integrations.ai import generate_text
from .issues import MAX_DESCRIPTION_CHARS, MIN_DESCRIPTION_CHARS, describe_issues
from .text import content_words, extract_sentences

log = logging.getLogger(__name__)

MAX_SHORT_CHARS = 450

# Every input character is billed. Stored descriptions reach ~3,000 characters,
# but the audit only has to produce 700, and the opening of a description is
# where the genre, setting and gameplay always are — so the tail is paid-for
# context that changes nothing. Cutting here roughly halves the cost per call.
_MAX_GROQ_INPUT_CHARS = 2_000
_MAX_REASON_CHARS = 200
_AUDIT_MAX_OUTPUT_TOKENS = 400
_AUDIT_TEMPERATURE = 0.2
_ALLOWED_VERDICTS = frozenset({"OK", "CLEANED", "UNUSABLE"})
# Not a model answer: what we return when Groq replied but its rewrite failed
# validation. Distinct from None so the caller knows the provider is still up.
REJECTED_VERDICT = "REJECTED"
# Share of the rewrite's content words that must also appear in the source text
# or the title. A faithful cleanup reuses most of them; a fabrication does not.
_MIN_SOURCE_OVERLAP = 0.25

_AUDIT_PROMPT = (
    "You audit one video-game description for a game catalog. Judge only the "
    "supplied text and never add facts from outside it. "
    "Return compact JSON with keys verdict, summary and reason. "
    "verdict is OK when the text already reads as a clean, factual description "
    "of the named game. CLEANED when you can turn the supplied text into one by "
    "removing marketing, storefront and boilerplate lines, repairing broken "
    "wording or encoding, translating it into English, or shortening it. "
    "UNUSABLE when the text is nonsense, describes a different product, or says "
    "nothing about the game. "
    "For CLEANED, summary is the corrected description: 2-5 sentences of plain "
    "English prose covering genre, core gameplay, setting and tone, "
    f"under {MAX_DESCRIPTION_CHARS} characters, with no markup, links, review "
    "scores, prices, platform lists or calls to action. "
    "For OK and UNUSABLE, summary is an empty string. "
    "reason is at most one short sentence."
)
_SHORTEN_PROMPT = (
    "You are a game description writer. "
    "Write a short paragraph of 3-4 sentences describing the given game. "
    "Capture the genre, core gameplay style, setting, and tone. "
    "Do NOT mention review scores, awards, prices, or platform names. "
    f"Stay strictly under {MAX_SHORT_CHARS} characters. "
    "Write in English. Return only the description, no extra text."
)


@dataclass(frozen=True)
class DescriptionVerdict:
    """One audit outcome: OK, CLEANED, UNUSABLE or REJECTED_VERDICT."""

    verdict: str
    summary: str
    reason: str


async def audit_description(
    title: str,
    text: str,
    issues: list[str],
) -> DescriptionVerdict | None:
    """Provider-chain judgement, or None when every configured provider failed."""
    payload = json.dumps(
        {"title": title, "issues": issues, "description": _bounded_input(text)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    answer = await generate_text(
        _AUDIT_PROMPT,
        payload,
        max_output_tokens=_AUDIT_MAX_OUTPUT_TOKENS,
        temperature=_AUDIT_TEMPERATURE,
        json_object=True,
        response_validator=_valid_audit_response,
    )
    if answer is None:
        return None
    verdict = parse_audit_answer(answer)
    if verdict is None:
        log.debug("AI description audit response was not valid JSON")
        return None
    if verdict.verdict != "CLEANED":
        return verdict
    accepted = _accept_rewrite(title, text, verdict.summary)
    if accepted is None:
        log.debug("Rejected AI rewrite for %r", title)
        return DescriptionVerdict(REJECTED_VERDICT, "", verdict.reason)
    return DescriptionVerdict("CLEANED", accepted, verdict.reason)


def _bounded_input(text: str) -> str:
    """Cap the text we pay for, cutting at a sentence boundary where possible.

    A hard character cut leaves a dangling fragment the model then reproduces as
    a truncated rewrite — which our own validation would reject.
    """
    if len(text) <= _MAX_GROQ_INPUT_CHARS:
        return text
    return extract_sentences(text, _MAX_GROQ_INPUT_CHARS)


def parse_audit_answer(answer: str | None) -> DescriptionVerdict | None:
    if not answer:
        return None
    start = answer.find("{")
    end = answer.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(answer[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    verdict = str(payload.get("verdict") or "").strip().upper()
    if verdict not in _ALLOWED_VERDICTS:
        return None
    raw_summary = payload.get("summary")
    summary = raw_summary.strip() if isinstance(raw_summary, str) else ""
    reason = str(payload.get("reason") or "").strip()[:_MAX_REASON_CHARS]
    return DescriptionVerdict(verdict=verdict, summary=summary, reason=reason)


def _valid_audit_response(answer: str) -> bool:
    return parse_audit_answer(answer) is not None


def _accept_rewrite(title: str, source: str, rewrite: str) -> str | None:
    """Return the rewrite when it is publishable, otherwise None."""
    if not rewrite:
        return None
    if len(rewrite) > MAX_DESCRIPTION_CHARS:
        rewrite = extract_sentences(rewrite, MAX_DESCRIPTION_CHARS)
    if len(rewrite) < MIN_DESCRIPTION_CHARS or describe_issues(rewrite):
        return None
    if not _is_grounded(title, source, rewrite):
        return None
    return rewrite


def _is_grounded(title: str, source: str, rewrite: str) -> bool:
    """Reject rewrites that share almost no vocabulary with their source.

    Skipped when the source is not English: a translation legitimately shares
    nothing with it, and the length and content checks still apply.
    """
    if "non_english" in describe_issues(source):
        return True
    rewritten_words = content_words(rewrite)
    if not rewritten_words:
        return False
    known = content_words(source) | content_words(title)
    return len(rewritten_words & known) / len(rewritten_words) >= _MIN_SOURCE_OVERLAP


async def shorten_summary(title: str, summary: str) -> str:
    """Compact display blurb, falling back to a clean extract without AI."""
    generated = await generate_text(
        _SHORTEN_PROMPT,
        f"Game: {title}\n\nDescription: {_bounded_input(summary)}",
        max_output_tokens=180,
    )
    if not generated:
        return extract_short_summary(summary)
    if len(generated) > MAX_SHORT_CHARS:
        return extract_sentences(generated, MAX_SHORT_CHARS)
    return generated


def extract_short_summary(summary: str) -> str:
    """Compact display blurb taken straight from the description, no AI call."""
    return extract_sentences(summary, MAX_SHORT_CHARS)
