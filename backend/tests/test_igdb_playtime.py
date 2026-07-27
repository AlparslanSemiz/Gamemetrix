from app.integrations.igdb_playtime import (
    build_igdb_playtime_query,
    parse_igdb_playtimes_minutes,
)


def test_igdb_playtime_query_batches_and_deduplicates_ids() -> None:
    query = build_igdb_playtime_query([9, 2, 9, -1, 0])

    assert "where game_id = (2,9)" in query
    assert "limit 2" in query


def test_igdb_playtime_parser_keeps_each_games_main_time() -> None:
    rows = [
        {"game_id": 2, "normally": 7200, "hastily": 3600},
        {"game_id": 9, "normally": 0, "hastily": 1800},
        {"game_id": 10, "normally": None, "hastily": None, "completely": 10800},
        {"game_id": "bad", "normally": 1200},
    ]

    assert parse_igdb_playtimes_minutes(rows) == {2: 120, 9: 30, 10: 180}
