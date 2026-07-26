"""Deterministic description-quality checks and the mechanical repair pass.

Every issue here is decided without spending an AI call. The batch runs the
sanitizer first and only escalates to AI what mechanical repair cannot settle
— junk prose, text describing a different game, wrong language — because the
shared AI batch budget is a few calls against a catalog of tens of
thousands of rows.

Public API:
  describe_issues(text)   -> list[str]
  sanitize_description(t) -> str
  needs_ai_review(issues) -> bool
  is_unfixable(issues)    -> bool
"""

import re

from ..metadata import (
    looks_like_placeholder,
    looks_like_promo,
    repair_mojibake,
    strip_markup,
    strip_promo,
)
from .text import ends_mid_sentence, split_sentences

MIN_DESCRIPTION_CHARS = 80
MAX_DESCRIPTION_CHARS = 700

_MIN_SHOUTING_CHARS = 40
_MAX_UPPERCASE_RATIO = 0.5
_MIN_LATIN_RATIO = 0.6
_MIN_SENTENCES_FOR_REPETITION = 3

_MOJIBAKE_MARKERS: tuple[str, ...] = ("â€", "Ã©", "Ã¼", "Â©", "Â®", "ï¿½", "�")
_BOILERPLATE_MARKERS: tuple[str, ...] = (
    "©",
    "all rights reserved",
    "trademarks are property",
    "read more",
    "click here",
    "source: wikipedia",
    "this article",
    "@",
)
_MARKUP_RE = re.compile(r"<[^>]+>|&(?:amp|lt|gt|quot|#\d+);|\[/?\w+\]|^\s*[*\-•]\s", re.MULTILINE)
# A heading inside a game description is always a section label ("About",
# "Story", "Key Features"), never prose — drop it with its text.
_HEADING_RE = re.compile(r"<h[1-6][^>]*>.*?</h[1-6]>", re.IGNORECASE | re.DOTALL)
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_REPEATED_CHAR_RE = re.compile(r"(.)\1{5,}")
_LATIN_RE = re.compile(r"[A-Za-z]")
_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)

# Placeholder text has no facts to rewrite from — a fresh provider fetch is the
# only honest repair, so it never reaches the AI.
_UNFIXABLE_ISSUES = frozenset({"empty", "placeholder"})


def describe_issues(text: str) -> list[str]:
    """Reasons this description is not presentable, cheapest checks first."""
    stripped = text.strip()
    if not stripped:
        return ["empty"]
    if looks_like_placeholder(stripped):
        return ["placeholder"]

    issues: list[str] = []
    if _MARKUP_RE.search(stripped):
        issues.append("markup")
    if any(marker in stripped for marker in _MOJIBAKE_MARKERS):
        issues.append("encoding")
    if looks_like_promo(stripped):
        issues.append("promo")
    if _URL_RE.search(stripped) or any(
        marker in stripped.casefold() for marker in _BOILERPLATE_MARKERS
    ):
        issues.append("boilerplate")
    if _REPEATED_CHAR_RE.search(stripped):
        issues.append("repeated_characters")
    if len(stripped) < MIN_DESCRIPTION_CHARS:
        issues.append("too_short")
    if len(stripped) > MAX_DESCRIPTION_CHARS:
        issues.append("too_long")
    if ends_mid_sentence(stripped):
        issues.append("truncated")
    if _is_shouting(stripped):
        issues.append("shouting")
    if not _is_latin_script(stripped):
        issues.append("non_english")
    if _has_repeated_sentences(stripped):
        issues.append("duplicate_sentences")
    return issues


def sanitize_description(text: str) -> str:
    """Mechanical repair: markup, encoding, promo and boilerplate sentences."""
    cleaned = repair_mojibake(strip_markup(_HEADING_RE.sub(" ", text)))
    cleaned = _REPEATED_CHAR_RE.sub(lambda match: match.group(1) * 2, cleaned)
    cleaned = strip_promo(cleaned)
    cleaned = _drop_boilerplate_sentences(cleaned)
    return _dedupe_sentences(cleaned).strip()


def needs_ai_review(issues: list[str]) -> bool:
    """True when a description still has issues after the mechanical pass."""
    return any(issue not in _UNFIXABLE_ISSUES for issue in issues)


def is_unfixable(issues: list[str]) -> bool:
    return any(issue in _UNFIXABLE_ISSUES for issue in issues)


def _drop_boilerplate_sentences(text: str) -> str:
    kept = [
        sentence
        for sentence in split_sentences(text)
        if not _URL_RE.search(sentence)
        and not any(marker in sentence.casefold() for marker in _BOILERPLATE_MARKERS)
    ]
    return " ".join(kept) if kept else text


def _dedupe_sentences(text: str) -> str:
    seen: set[str] = set()
    kept: list[str] = []
    for sentence in split_sentences(text):
        key = sentence.casefold()
        if key in seen:
            continue
        seen.add(key)
        kept.append(sentence)
    return " ".join(kept)


def _has_repeated_sentences(text: str) -> bool:
    sentences = [sentence.casefold() for sentence in split_sentences(text)]
    if len(sentences) < _MIN_SENTENCES_FOR_REPETITION:
        return False
    return len(set(sentences)) < len(sentences)


def _is_shouting(text: str) -> bool:
    letters = _LETTER_RE.findall(text)
    if len(letters) < _MIN_SHOUTING_CHARS:
        return False
    uppercase = sum(1 for letter in letters if letter.isupper())
    return uppercase / len(letters) > _MAX_UPPERCASE_RATIO


def _is_latin_script(text: str) -> bool:
    letters = _LETTER_RE.findall(text)
    if not letters:
        return False
    return len(_LATIN_RE.findall(text)) / len(letters) >= _MIN_LATIN_RATIO
