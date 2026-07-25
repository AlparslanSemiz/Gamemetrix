from unittest.mock import Mock

from app.integrations.rawg.detail import rawg_relations_for_fields
from app.services.metadata_backfill.sources import source_needed
from tests.test_seo import game_fixture


def _complete_metadata_game():
    return game_fixture(
        developer="Example Studio",
        publisher="Example Publisher",
        game_modes=["Single player"],
        website_url="https://example.test/game",
        screenshots=["https://images.example/screenshot.jpg"],
        system_requirements=[{"minimum": "Any"}],
        dlcs=[{"name": "Expansion"}],
        similar_games=[{"name": "Related Game"}],
    )


def test_rawg_is_not_spent_only_to_add_an_external_id() -> None:
    db = Mock()

    assert source_needed(db, _complete_metadata_game(), "RAWG") is False
    db.scalar.assert_not_called()


def test_rawg_related_endpoints_are_requested_only_for_matching_gaps() -> None:
    assert rawg_relations_for_fields({"summary", "cover"}) == ()
    assert rawg_relations_for_fields({"dlcs"}) == ("additions",)
    assert rawg_relations_for_fields({"similar_games"}) == ("game-series",)
    assert rawg_relations_for_fields(None) == ("additions", "game-series")
