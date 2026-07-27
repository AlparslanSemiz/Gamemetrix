from app.integrations.igdb_import import _game_from_igdb


def test_igdb_catalog_row_respects_database_string_limits() -> None:
    raw = {
        "id": 123,
        "name": "A" * 400,
        "slug": "s" * 400,
        "url": "https://example.com/" + ("u" * 700),
        "involved_companies": [
            {
                "company": {"name": "Developer " + ("d" * 300)},
                "developer": True,
                "publisher": True,
            }
        ],
    }

    game = _game_from_igdb(raw)

    assert len(game.title) <= 160
    assert len(game.slug) <= 180
    assert game.developer is not None and len(game.developer) <= 200
    assert game.publisher is not None and len(game.publisher) <= 200
