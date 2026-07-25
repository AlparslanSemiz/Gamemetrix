import pytest
from pydantic import ValidationError

from app.routers.account.schemas import CollectionsPayload
from app.schemas import GameSlugBatchRequest
from app.services.account_state import COLLECTION_TYPES


def test_collection_contract_includes_on_hold_and_dropped() -> None:
    payload = CollectionsPayload(
        on_hold=["paused-game"],
        dropped=["abandoned-game"],
    )

    assert "on_hold" in COLLECTION_TYPES
    assert "dropped" in COLLECTION_TYPES
    assert payload.on_hold == ["paused-game"]
    assert payload.dropped == ["abandoned-game"]


def test_game_slug_batch_deduplicates_and_validates_slugs() -> None:
    payload = GameSlugBatchRequest(slugs=["first-game", "second-game", "first-game"])
    assert payload.slugs == ["first-game", "second-game"]

    with pytest.raises(ValidationError):
        GameSlugBatchRequest(slugs=["../invalid"])
