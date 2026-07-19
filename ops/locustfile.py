"""
Locust load test for GameMetrix's public read endpoints.

Run this from YOUR LOCAL MACHINE, not on the 1GB VM — the load generator
needs its own CPU/RAM, and running it alongside the app it's hammering would
skew every result.

Install & run:
    pip install locust
    locust -f ops/locustfile.py --host http://gamemetrix.me

Then open http://localhost:8089 to set concurrent users / ramp-up and start.
Headless one-liner (50 users, 5/s ramp-up, 3 minutes):
    locust -f ops/locustfile.py --host http://gamemetrix.me \
        --headless -u 50 -r 5 -t 3m --csv=ops/results/run1

While it runs, watch the SERVER side in a separate SSH session:
    watch -n1 docker stats
    tail -f /var/log/gamemetrix-memwatch.log
    dmesg -T | grep -i -e oom -e killed   # confirms/rules out OOM kills
"""

import random

from locust import HttpUser, task, between


# A mix of real-looking search terms — hitting titles likely already cached
# in the DB exercises the fast path; a couple of long-tail terms occasionally
# fall through to the RAWG lookup (see routers/games.py:search_game), which
# is the expensive path worth watching under load.
SEARCH_TERMS = [
    "zelda", "witcher", "elden ring", "hollow knight", "stardew",
    "cyberpunk", "hades", "portal", "half life", "baldur",
    "celeste", "dark souls", "minecraft", "terraria", "outer wilds",
]

GENRES = ["action", "rpg", "indie", "strategy", None]
SORTS = ["rank_score", "metacritic_score", "review_count"]


class GameMetrixUser(HttpUser):
    # Real users pause between actions; this also keeps Locust from
    # generating a request rate no real client would ever produce.
    wait_time = between(1, 3)

    def on_start(self):
        self.known_slugs: list[str] = []

    @task(6)
    def list_games(self):
        params = {
            "limit": random.choice([24, 60, 120]),
            "offset": random.choice([0, 24, 60]),
            "sort": random.choice(SORTS),
            "direction": random.choice(["asc", "desc"]),
        }
        genre = random.choice(GENRES)
        if genre:
            params["genre"] = genre

        with self.client.get("/api/games", params=params, name="/api/games", catch_response=True) as resp:
            self._handle_response(resp)
            if resp.status_code == 200:
                try:
                    items = resp.json().get("items", [])
                    self.known_slugs.extend(g["slug"] for g in items if "slug" in g)
                    self.known_slugs = self.known_slugs[-200:]  # bounded cache
                except ValueError:
                    pass

    @task(2)
    def search_game(self):
        term = random.choice(SEARCH_TERMS)
        with self.client.get(
            "/api/search", params={"q": term}, name="/api/search", catch_response=True
        ) as resp:
            self._handle_response(resp, extra_ok={404, 400, 502})

    @task(2)
    def game_detail(self):
        if not self.known_slugs:
            return  # nothing seen yet — list_games seeds this
        slug = random.choice(self.known_slugs)
        with self.client.get(f"/api/games/{slug}", name="/api/games/[slug]", catch_response=True) as resp:
            self._handle_response(resp, extra_ok={404})

    @task(1)
    def facets(self):
        with self.client.get("/api/facets", name="/api/facets", catch_response=True) as resp:
            self._handle_response(resp)

    def _handle_response(self, resp, extra_ok: set[int] = frozenset()):
        """429 = the app's own rate limiter (slowapi) doing its job — that's
        a PASS, not a failure. Only 5xx/timeouts represent a real problem."""
        if resp.status_code == 429:
            resp.success()
        elif resp.status_code == 200 or resp.status_code in extra_ok:
            resp.success()
        else:
            resp.failure(f"unexpected status {resp.status_code}")
