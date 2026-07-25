from unittest.mock import Mock

from app.models import Game
from app.services.deduplication import (
    add_duplicate_candidate,
    find_existing_duplicate,
)


def _game(game_id: int, title: str, slug: str, year: int = 2020) -> Game:
    return Game(
        id=game_id,
        title=title,
        slug=slug,
        summary="",
        cover_url="",
        release_date=f"{year}-01-01",
        release_year=year,
        metrix_score=0,
        critic_score=0,
        user_score=0,
        genres=[],
        platforms=[],
        source_scores=[],
        content_type="game",
    )


def test_indexed_duplicate_lookup_only_fetches_matching_candidates() -> None:
    existing = _game(1, "Portal 2", "portal-2")
    unrelated = _game(2, "Hades", "hades")
    candidate = _game(0, "Portal II", "portal-ii-igdb")
    index = {}
    add_duplicate_candidate(index, existing)
    add_duplicate_candidate(index, unrelated)

    db = Mock()
    db.scalars.return_value.all.return_value = [existing]

    assert find_existing_duplicate(db, candidate, candidate_index=index) is existing
    statement = db.scalars.call_args.args[0]
    assert "games.id IN" in str(statement)


def test_indexed_duplicate_lookup_avoids_database_for_unrelated_title() -> None:
    existing = _game(1, "Hades", "hades")
    candidate = _game(0, "Portal 2", "portal-2-igdb")
    index = {}
    add_duplicate_candidate(index, existing)

    db = Mock()

    assert find_existing_duplicate(db, candidate, candidate_index=index) is None
    db.scalars.assert_not_called()
