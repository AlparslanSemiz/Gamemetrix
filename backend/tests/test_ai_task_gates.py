from datetime import UTC, datetime, timedelta

from app.models import Game
from app.services import endless as endless_module
from app.services.similarity import ai_rerank


def _game(**overrides: object) -> Game:
    values: dict[str, object] = {
        "id": 1,
        "title": "Example Game",
        "slug": "example-game",
        "summary": "A tactical adventure with exploration and a story campaign.",
        "summary_short": "",
        "genres": ["Adventure"],
        "game_modes": ["Single-player"],
        "platforms": ["PC"],
        "source_scores": [],
        "content_type": "game",
        "rank_score": 80.0,
        "metrix_score": 80.0,
    }
    values.update(overrides)
    return Game(**values)


def test_endless_classification_runs_only_for_new_or_changed_metadata() -> None:
    checked_at = datetime.now(UTC)
    game = _game(endless_checked_at=checked_at, metadata_refreshed_at=checked_at - timedelta(days=1))

    assert endless_module.needs_endless_check(game) is False

    game.metadata_refreshed_at = checked_at + timedelta(seconds=1)
    assert endless_module.needs_endless_check(game) is True

    game.metadata_refreshed_at = checked_at - timedelta(days=1)
    game.hltb_refreshed_at = checked_at + timedelta(seconds=1)
    assert endless_module.needs_endless_check(game) is True

    game.endless_checked_at = None
    assert endless_module.needs_endless_check(game) is True


def test_similarity_ai_is_skipped_when_algorithm_has_a_clear_order() -> None:
    source = _game()
    clear = _game(
        id=2,
        slug="clear",
        title="Example Game II",
        developer="Same Studio",
        genres=["Adventure"],
        rank_score=95.0,
    )
    distant = _game(
        id=3,
        slug="distant",
        title="Unrelated Racer",
        developer="Other Studio",
        genres=["Racing"],
        rank_score=20.0,
    )

    assert ai_rerank.needs_ai_rerank(source, [clear, distant], limit=1) is False


def test_similarity_ai_is_allowed_for_an_ambiguous_cutoff() -> None:
    source = _game()
    first = _game(id=2, slug="first", title="First", genres=["Adventure"], rank_score=80.0)
    second = _game(id=3, slug="second", title="Second", genres=["Adventure"], rank_score=79.0)

    assert ai_rerank.needs_ai_rerank(source, [first, second], limit=1) is True
