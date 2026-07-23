"""Turning Steam's HTML-ish store fields into plain values."""

import re
from datetime import date, datetime
from html import unescape
from urllib.parse import urlparse

_DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%d %b, %Y", "%d %B, %Y")
_UNRELEASED_MARKERS = ("coming soon", "to be announced")
_MAX_URL_LENGTH = 500
_REQUIREMENT_LABEL_ONLY = {"minimum:", "recommended:", "minimum", "recommended"}


def parse_release_date(value: str | None) -> date | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized or any(marker in normalized.lower() for marker in _UNRELEASED_MARKERS):
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    return None


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.replace("\r", "")
    text = re.sub(r"(?i)<\s*br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "", text)
    text = re.sub(r"(?i)</?(?:ul|p|div)[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip(" -•\t") for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def clean_requirement_block(value: str | None) -> str:
    text = html_to_text(value)
    if not text or text.lower().strip() in _REQUIREMENT_LABEL_ONLY:
        return ""
    return text


def clean_website_url(value: str | None) -> str | None:
    if not value:
        return None
    url = value.strip()
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url[:_MAX_URL_LENGTH]
