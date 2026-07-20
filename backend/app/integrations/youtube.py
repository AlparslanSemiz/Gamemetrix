import re
from urllib.parse import quote_plus

import httpx

from ..config import USER_AGENT


_YOUTUBE_SEARCH_URL = "https://www.youtube.com/results"
_VIDEO_ID_RE = re.compile(r"watch\?v=([A-Za-z0-9_-]{11})")
_HTTP_TIMEOUT = 12


async def find_trailer_video_id(title: str) -> str | None:
    query = quote_plus(f"{title} official trailer game")
    headers = {
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": f"Mozilla/5.0 {USER_AGENT}",
    }

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=headers, follow_redirects=True) as client:
        response = await client.get(f"{_YOUTUBE_SEARCH_URL}?search_query={query}")
        if not response.is_success:
            return None

    seen: set[str] = set()
    for match in _VIDEO_ID_RE.finditer(response.text):
        video_id = match.group(1)
        if video_id not in seen:
            seen.add(video_id)
            return video_id
    return None
