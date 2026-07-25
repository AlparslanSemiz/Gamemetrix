from datetime import date

import pytest

from app.config import Settings
from app.integrations.gamebrain_service import GameBrainService
from app.integrations.igdb_import import build_full_catalog_query
from app.integrations.steam_catalog import catalog_request_input, parse_catalog_page
from app.integrations.wikidata_service import WikidataService


def test_full_igdb_query_uses_game_type_and_keyset_pagination() -> None:
    query = build_full_catalog_query(after_id=1234, page_size=500)

    assert "game_type = 0" in query
    assert "category =" not in query
    assert "total_rating_count" not in query.split("where", 1)[1]
    assert "id > 1234" in query
    assert "sort id asc" in query
    assert "limit 500" in query


def test_steam_catalog_request_only_includes_games() -> None:
    payload = catalog_request_input(last_appid=620, max_results=500)

    assert payload["last_appid"] == 620
    assert payload["max_results"] == 500
    assert payload["include_games"] is True
    assert payload["include_dlc"] is False
    assert payload["include_software"] is False
    assert payload["include_videos"] is False
    assert payload["include_hardware"] is False


def test_steam_catalog_page_parses_official_response_shape() -> None:
    page = parse_catalog_page({
        "response": {
            "apps": [
                {"appid": 620, "name": "Portal 2", "last_modified": 123},
                {"appid": "invalid", "name": "Broken"},
            ],
            "have_more_results": True,
            "last_appid": 620,
        }
    })

    assert page.apps == [(620, "Portal 2", 123)]
    assert page.have_more is True
    assert page.last_appid == 620


def test_wikidata_normalization_aggregates_rows_for_one_exact_identity() -> None:
    normalized = WikidataService().normalize_bindings([
        {
            "item": {"value": "http://www.wikidata.org/entity/Q500"},
            "itemLabel": {"value": "Portal 2"},
            "releaseDate": {"value": "2011-04-18T00:00:00Z"},
            "developerLabel": {"value": "Valve"},
            "publisherLabel": {"value": "Valve"},
            "genreLabel": {"value": "puzzle-platform game"},
            "platformLabel": {"value": "Microsoft Windows"},
            "website": {"value": "https://www.thinkwithportals.com/"},
            "steamId": {"value": "620"},
            "igdbSlug": {"value": "portal-2"},
        },
        {
            "item": {"value": "http://www.wikidata.org/entity/Q500"},
            "itemLabel": {"value": "Portal 2"},
            "genreLabel": {"value": "first-person video game"},
            "platformLabel": {"value": "Linux"},
        },
    ])

    assert normalized is not None
    assert normalized.external_id == "Q500"
    assert normalized.name == "Portal 2"
    assert normalized.release_date == date(2011, 4, 18)
    assert normalized.developer == "Valve"
    assert normalized.publisher == "Valve"
    assert normalized.genres == ["puzzle-platform game", "first-person video game"]
    assert normalized.platforms == ["PC", "Linux"]
    assert normalized.raw["steam_app_id"] == 620
    assert normalized.raw["igdb_slug"] == "portal-2"


def test_gamebrain_normalization_keeps_metadata_supplementary() -> None:
    normalized = GameBrainService().normalize_detail({
        "id": 1273796,
        "name": "Kingdom Come: Deliverance II",
        "release_date": "2025-02-04",
        "developer": "Warhorse Studios",
        "short_description": "A historical open-world role-playing game.",
        "image": "https://img.gamebrain.co/game.jpg",
        "link": "https://gamebrain.co/game/kingdom-come-deliverance-2",
        "genres": [{"name": "Role Playing"}, {"name": "Action"}],
        "platforms": [{"name": "PC"}, {"name": "Playstation 5"}],
        "play_modes": [{"name": "Single-Player"}],
        "screenshots": ["https://img.gamebrain.co/screenshot.jpg"],
        "official_stores": [
            {"source": "steam", "url": "https://store.steampowered.com/app/1771300"}
        ],
        "rating": {"mean": 0.9, "count": 100},
    })

    assert normalized.external_id == "1273796"
    assert normalized.release_date == date(2025, 2, 4)
    assert normalized.developer == "Warhorse Studios"
    assert normalized.genres == ["Role Playing", "Action"]
    assert normalized.platforms == ["PC", "PlayStation 5"]
    assert normalized.game_modes == ["singleplayer"]
    assert normalized.score is None
    assert normalized.raw["steam_app_id"] == 1771300


def test_gamebrain_free_plan_requires_explicit_noncommercial_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GAMEBRAIN_API_KEY", "test-key")
    monkeypatch.delenv("GAMEBRAIN_NONCOMMERCIAL_ENABLED", raising=False)
    monkeypatch.delenv("GAMEBRAIN_CACHE_PERMISSION_GRANTED", raising=False)
    assert Settings().gamebrain_configured() is False

    monkeypatch.setenv("GAMEBRAIN_NONCOMMERCIAL_ENABLED", "true")
    assert Settings().gamebrain_configured() is False

    monkeypatch.setenv("GAMEBRAIN_CACHE_PERMISSION_GRANTED", "true")
    assert Settings().gamebrain_configured() is True
