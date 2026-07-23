"""In-memory deduplication of a game list, keeping the best copy of each title."""

from collections import defaultdict

from ...models import Game
from .matching import duplicate_key, duplicate_quality_key, games_are_duplicates


def dedupe_games_in_memory(games: list[Game]) -> list[Game]:
    deduped: list[Game] = []
    idx_by_key: dict[str, list[int]] = defaultdict(list)

    def register(game: Game, idx: int) -> None:
        for key in set(duplicate_key(game)):
            if key and idx not in idx_by_key[key]:
                idx_by_key[key].append(idx)

    def find_match(game: Game) -> int | None:
        for key in set(duplicate_key(game)):
            for idx in idx_by_key.get(key, []):
                if games_are_duplicates(deduped[idx], game):
                    return idx
        return None

    for game in games:
        existing_idx = find_match(game)
        if existing_idx is None:
            new_idx = len(deduped)
            deduped.append(game)
            register(game, new_idx)
        elif duplicate_quality_key(game) > duplicate_quality_key(deduped[existing_idx]):
            deduped[existing_idx] = game
            register(game, existing_idx)

    return deduped
