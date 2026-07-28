from app.integrations.igdb_import import _game_from_igdb, build_full_catalog_query


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


def test_igdb_catalog_row_imports_official_website_and_game_modes() -> None:
    raw = {
        "id": 123,
        "name": "Example Game",
        "websites": [
            {"url": "https://store.steampowered.com/app/123", "type": 13},
            {"url": "https://example-game.test", "type": 1, "trusted": True},
        ],
        "game_modes": [{"name": "Single player"}, {"name": "Co-operative"}],
        "external_games": [
            {
                "category": 1,
                "uid": "620",
                "url": "https://store.steampowered.com/app/620",
            }
        ],
    }

    game = _game_from_igdb(raw)

    assert game.website_url == "https://example-game.test"
    assert game.game_modes == ["singleplayer", "coop"]
    assert game.steam_app_id == 620


def test_full_catalog_query_requests_official_website_and_game_modes() -> None:
    query = build_full_catalog_query(after_id=0)

    assert "websites.url" in query
    assert "websites.type" in query
    assert "game_modes.name" in query
    assert "external_games.uid" in query
    assert "external_games.category" in query
