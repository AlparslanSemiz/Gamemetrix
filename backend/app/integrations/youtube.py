import re
from urllib.parse import quote_plus

import httpx


YOUTUBE_SEARCH_URL = "https://www.youtube.com/results"
VIDEO_ID_RE = re.compile(r"watch\?v=([A-Za-z0-9_-]{11})")


async def find_trailer_video_id(title: str) -> str | None:
    query = quote_plus(f"{title} official trailer game")
    headers = {
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 GameMetrix/0.1",
    }

    async with httpx.AsyncClient(timeout=12, headers=headers, follow_redirects=True) as client:
        response = await client.get(f"{YOUTUBE_SEARCH_URL}?search_query={query}")
        if not response.is_success:
            return None

    seen: set[str] = set()
    for match in VIDEO_ID_RE.finditer(response.text):
        video_id = match.group(1)
        if video_id in seen:
            continue
        seen.add(video_id)
        return video_id

    return None
