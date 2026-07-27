from app.integrations.types import NormalizedGame
from app.services.metadata_backfill.apply import apply_normalized_game
from app.services.metadata_backfill.gaps import field_gaps
from tests.test_seo import game_fixture


def test_optional_metadata_does_not_keep_a_game_in_the_backfill_queue() -> None:
    game = game_fixture(
        developer="Example Studio",
        publisher="Example Publisher",
        game_modes=[],
        website_url=None,
        screenshots=["https://images.example/screenshot.jpg"],
        system_requirements=[{"platform": "PC", "minimum": "Windows 10"}],
        dlcs=[],
        similar_games=[],
    )

    assert field_gaps(game) == set()


def test_system_requirements_are_required_only_for_pc_games() -> None:
    pc_game = game_fixture(
        developer="Example Studio",
        publisher="Example Publisher",
        screenshots=["https://images.example/screenshot.jpg"],
        platforms=["PC"],
        system_requirements=[],
    )
    switch_game = game_fixture(
        developer="Example Studio",
        publisher="Example Publisher",
        screenshots=["https://images.example/screenshot.jpg"],
        platforms=["Nintendo Switch"],
        system_requirements=[],
    )

    assert "system_requirements" in field_gaps(pc_game)
    assert "system_requirements" not in field_gaps(switch_game)


def test_metadata_applier_uses_official_website_not_provider_profile() -> None:
    game = game_fixture(website_url=None)
    result = NormalizedGame(
        source="IGDB",
        external_id="123",
        name=game.title,
        external_url="https://www.igdb.com/games/example",
        raw={"website": "https://example-game.test"},
    )

    assert apply_normalized_game(game, result, trusted=True) is True
    assert game.website_url == "https://example-game.test"


def test_metadata_applier_repairs_known_provider_profile_url() -> None:
    game = game_fixture(website_url="https://www.igdb.com/games/example")
    result = NormalizedGame(
        source="IGDB",
        external_id="123",
        name=game.title,
        raw={"website": "https://example-game.test"},
    )

    assert apply_normalized_game(game, result, trusted=True) is True
    assert game.website_url == "https://example-game.test"
