from datetime import date

from app.models import Game
from app.services.seo import seo_exclusion_reason, sitemap_document


def game_fixture(**overrides) -> Game:
    values = {
        "id": 1,
        "title": "A Complete Test Game",
        "slug": "a-complete-test-game",
        "summary": " ".join(["A meaningful independently written game summary with useful player context."] * 4),
        "summary_short": None,
        "cover_url": "https://images.example/game.jpg",
        "image_url": None,
        "website_url": None,
        "release_date": date(2024, 4, 12),
        "release_year": 2024,
        "content_type": "game",
        "metrix_score": 86,
        "rank_score": 82,
        "is_rankable": True,
        "seo_indexable": False,
        "seo_exclusion_reason": None,
        "critic_score": 85,
        "user_score": 87,
        "genres": ["RPG"],
        "platforms": ["PC"],
        "source_scores": [
            {"source": "Metacritic", "score": 86, "scale": 100, "status": "live"},
            {"source": "Steam", "score": 88, "scale": 100, "status": "live", "review_count": 500},
        ],
        "playtime_minutes": 0,
        "hltb_main_story_minutes": 0,
        "hltb_main_extra_minutes": 0,
        "hltb_completionist_minutes": 0,
        "hltb_all_styles_minutes": 0,
        "proton_tier": "gold",
        "award_count": 0,
        "award_nominations": 0,
        "goty_year": None,
        "awards": [],
        "screenshots": [],
        "system_requirements": [],
        "dlcs": [],
        "similar_games": [],
    }
    values.update(overrides)
    return Game(**values)


def test_quality_gate_accepts_complete_game() -> None:
    assert seo_exclusion_reason(game_fixture(), has_price_data=False) is None


def test_quality_gate_rejects_thin_and_single_source_games() -> None:
    assert seo_exclusion_reason(
        game_fixture(summary="Too short"), has_price_data=False
    ) == "thin_summary"
    assert seo_exclusion_reason(game_fixture(source_scores=[
        {"source": "Steam", "score": 88, "scale": 100, "status": "live"},
    ]), has_price_data=False) == "insufficient_primary_scores"


def test_quality_gate_rejects_invalid_images_and_out_of_range_scores() -> None:
    assert seo_exclusion_reason(
        game_fixture(cover_url="https://"), has_price_data=False
    ) == "missing_image"
    assert seo_exclusion_reason(game_fixture(
        source_scores=[
            {"source": "Metacritic", "score": 101, "scale": 100, "status": "live"},
            {"source": "Steam", "score": 88, "scale": 100, "status": "live"},
        ],
    ), has_price_data=False) == "insufficient_primary_scores"
    assert seo_exclusion_reason(game_fixture(source_scores=[
        {"source": "RAWG", "score": 99, "scale": 100, "status": "live"},
        {"source": "Steam", "score": 88, "scale": 100, "status": "live"},
    ]), has_price_data=False) == "insufficient_primary_scores"


def test_price_data_alone_satisfies_decision_context() -> None:
    no_context = game_fixture(proton_tier=None)
    assert seo_exclusion_reason(no_context, has_price_data=False) == "missing_decision_context"
    assert seo_exclusion_reason(no_context, has_price_data=True) is None


def test_sitemap_contains_only_supplied_canonical_urls() -> None:
    game = game_fixture(seo_indexable=True)
    document = sitemap_document([game], [2024])
    assert "https://gamemetrix.me/game/a-complete-test-game" in document
    assert "https://gamemetrix.me/best/games/2024" in document
    assert document.startswith('<?xml version="1.0"')
