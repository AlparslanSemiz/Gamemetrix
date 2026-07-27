from app.integrations.igdb_optional_metadata import (
    build_igdb_optional_metadata_query,
    parse_igdb_optional_metadata,
)


def test_optional_metadata_query_batches_ids() -> None:
    query = build_igdb_optional_metadata_query([9, 2, 9, 0])

    assert "where id = (2,9)" in query
    assert "websites.type" in query
    assert "game_modes.name" in query


def test_optional_metadata_parser_keeps_only_official_website() -> None:
    rows = [{
        "id": 2,
        "websites": [
            {"url": "https://store.steampowered.com/app/2", "type": 13},
            {"url": "https://example-game.test", "type": 1},
        ],
        "game_modes": [{"name": "Single player"}, {"name": "Co-operative"}],
    }]

    assert parse_igdb_optional_metadata(rows) == {
        2: {
            "website": "https://example-game.test",
            "game_modes": ["singleplayer", "coop"],
        }
    }
