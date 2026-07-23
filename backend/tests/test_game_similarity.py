from app.models import Game
from app.services.game_similarity import (
    _genre_similarity_score,
    _passes_similarity_gate,
    rank_similar_games,
)


def _game(
    game_id: int,
    title: str,
    slug: str,
    genres: list[str],
    summary: str,
    *,
    developer: str = "Studio",
    rank_score: float = 80,
) -> Game:
    return Game(
        id=game_id,
        title=title,
        slug=slug,
        genres=genres,
        summary=summary,
        summary_short="",
        developer=developer,
        rank_score=rank_score,
        metrix_score=rank_score,
        platforms=["PC"],
        content_type="game",
    )


def test_similarity_score_keeps_specialized_profile_weighting() -> None:
    source = _game(
        1,
        "Baldur Gate III",
        "baldur-gate-iii",
        ["RPG", "Strategy"],
        "A party based isometric tactical turn-based CRPG with dialogue choices.",
    )
    same_series = _game(
        2,
        "Baldur Gate II",
        "baldur-gate-ii",
        ["RPG", "Strategy"],
        "A party based isometric tactical CRPG.",
        rank_score=92,
    )
    shooter = _game(
        3,
        "Space Shooter",
        "space-shooter",
        ["Action", "Shooter"],
        "Fast paced first person shooter gunplay.",
        developer="Other",
        rank_score=90,
    )

    assert _genre_similarity_score(source, same_series) == 453.68
    assert _passes_similarity_gate(source, same_series) is True
    assert _genre_similarity_score(source, shooter) == -249.4
    assert _passes_similarity_gate(source, shooter) is False


def test_similarity_fallback_order_is_stable() -> None:
    source = _game(
        1,
        "Baldur Gate III",
        "baldur-gate-iii",
        ["RPG", "Strategy"],
        "A party based isometric tactical turn-based CRPG with dialogue choices.",
    )
    candidates = [
        _game(
            2,
            "Baldur Gate II",
            "baldur-gate-ii",
            ["RPG", "Strategy"],
            "A party based isometric tactical CRPG.",
            rank_score=92,
        ),
        _game(
            3,
            "Space Shooter",
            "space-shooter",
            ["Action", "Shooter"],
            "Fast paced first person shooter gunplay.",
            developer="Other",
            rank_score=90,
        ),
        _game(
            4,
            "Narrative RPG",
            "narrative-rpg",
            ["RPG"],
            "A dialogue rich narrative role playing mystery.",
            developer="Other",
            rank_score=75,
        ),
        _game(
            5,
            "Casual Quest",
            "casual-quest",
            ["RPG", "Casual"],
            "A casual action adventure.",
            developer="Other",
            rank_score=70,
        ),
    ]

    ranked = rank_similar_games(source, candidates, display_limit=4)

    assert [game.slug for game in ranked] == [
        "baldur-gate-ii",
        "narrative-rpg",
        "casual-quest",
        "space-shooter",
    ]
