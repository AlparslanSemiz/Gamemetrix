from datetime import UTC, date, datetime
from math import ceil

from app.config import get_settings
from app.models import Game
from app.services.seo import (
    SITEMAP_CHUNK_SIZE,
    SitemapEntry,
    breadcrumb_genre,
    game_url_sitemap,
    seo_exclusion_reason,
    sitemap_chunk_count,
    sitemap_index_document,
    static_url_sitemap,
)


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


def test_game_sitemap_lists_canonical_urls_with_lastmod() -> None:
    game = game_fixture(seo_indexable=True, seo_updated_at=datetime(2024, 4, 12, tzinfo=UTC))
    document = game_url_sitemap([game])
    assert document.startswith('<?xml version="1.0"')
    assert "<urlset" in document
    assert "<loc>https://gamemetrix.me/game/a-complete-test-game</loc>" in document
    assert "<lastmod>2024-04-12</lastmod>" in document


def test_static_sitemap_emits_priority_and_changefreq() -> None:
    entries = [
        SitemapEntry("https://gamemetrix.me/", "daily", "1.0"),
        SitemapEntry("https://gamemetrix.me/best/games/2024", "weekly", "0.6"),
    ]
    document = static_url_sitemap(entries, datetime(2024, 4, 12, tzinfo=UTC))
    assert "<loc>https://gamemetrix.me/</loc>" in document
    assert "<changefreq>daily</changefreq>" in document
    assert "<priority>1.0</priority>" in document
    assert "https://gamemetrix.me/best/games/2024" in document


def test_sitemap_index_references_children() -> None:
    document = sitemap_index_document(
        [
            ("https://gamemetrix.me/sitemap-static.xml", None),
            ("https://gamemetrix.me/sitemap-games-1.xml", datetime(2024, 4, 12, tzinfo=UTC)),
        ]
    )
    assert document.startswith('<?xml version="1.0"')
    assert "<sitemapindex" in document
    assert "<loc>https://gamemetrix.me/sitemap-static.xml</loc>" in document
    assert "<loc>https://gamemetrix.me/sitemap-games-1.xml</loc>" in document


def test_sitemap_chunk_count_is_at_least_one_and_caps_at_limit() -> None:
    limit = get_settings().SEO_INDEX_LIMIT
    expected_max = max(1, ceil(limit / SITEMAP_CHUNK_SIZE))
    assert sitemap_chunk_count(0) == 1
    assert sitemap_chunk_count(1) == 1
    assert sitemap_chunk_count(limit * 10) == expected_max


def test_breadcrumb_genre_skips_non_indexable_games() -> None:
    assert breadcrumb_genre(None, game_fixture(seo_indexable=False), 8) is None
