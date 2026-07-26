"""Pure text helpers shared by the description auditor and the shortener."""

import re

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_TERMINAL_PUNCTUATION = ".!?\"')]"


def split_sentences(text: str) -> list[str]:
    return [sentence for sentence in _SENTENCE_SPLIT_RE.split(text.strip()) if sentence]


def extract_sentences(text: str, max_chars: int) -> str:
    """Longest whole-sentence prefix that fits, or a word-boundary cut."""
    result = ""
    for sentence in split_sentences(text):
        candidate = f"{result} {sentence}".strip() if result else sentence
        if len(candidate) > max_chars:
            break
        result = candidate
    if result:
        return result
    return text[:max_chars].rsplit(" ", 1)[0].rstrip(".,;:") + "."


def ends_mid_sentence(text: str) -> bool:
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1] not in _TERMINAL_PUNCTUATION


def content_words(text: str) -> set[str]:
    """Lowercase alphanumeric tokens long enough to carry meaning."""
    return {word for word in re.findall(r"[\w']{4,}", text.casefold())}
