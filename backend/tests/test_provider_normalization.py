import pytest

from app.integrations.cheapshark_service import CheapSharkService
from app.integrations.igdb_service import IGDBService
from app.integrations.itad_service import _best_deal_summary, _history_low
from app.integrations.rawg_service import RAWGService
from app.integrations.steam_service import SteamService
from app.integrations.types import NormalizedGame, bounded_float, bounded_int


def test_untrusted_numeric_helpers_reject_unsafe_values() -> None:
    assert bounded_float("72.5", maximum=100) == 72.5
    assert bounded_float(float("nan"), maximum=100) is None
    assert bounded_float(float("inf"), maximum=100) is None
    assert bounded_float(-1, maximum=100) is None
    assert bounded_float(101, maximum=100) is None
    assert bounded_float(True, maximum=100) is None

    assert bounded_int("42") == 42
    assert bounded_int("42.5") is None
    assert bounded_int(-1) is None
    assert bounded_int(True) is None


def test_igdb_normalization_falls_back_from_an_invalid_score() -> None:
    normalized = IGDBService()._normalize({
        "id": 1,
        "name": "Portal 2",
        "rating": "NaN",
        "rating_count": -1,
        "total_rating": "91.25",
        "total_rating_count": "1200",
    })

    assert normalized.score == 91.2
    assert normalized.score_count == 1200


def test_rawg_normalization_bounds_supplementary_ratings() -> None:
    normalized = RAWGService()._normalize({
        "id": 1,
        "name": "Portal 2",
        "metacritic": 101,
        "rating": 4.5,
        "ratings_count": "not-a-count",
    })

    assert normalized.score == 90.0
    assert normalized.score_count is None
    assert normalized.is_critic_score is False


def test_cheapshark_normalization_preserves_free_and_rejects_bad_prices() -> None:
    free = CheapSharkService().normalize_deal({
        "dealID": "free",
        "title": "Free Game",
        "normalPrice": "0.00",
        "salePrice": "0.00",
        "savings": "0",
    })
    malformed = CheapSharkService().normalize_deal({
        "dealID": "bad",
        "title": "Bad Price",
        "normalPrice": "NaN",
        "salePrice": "-4",
        "savings": "999",
    })

    assert free.list_price == 0.0
    assert free.sale_price == 0.0
    assert malformed.list_price is None
    assert malformed.sale_price is None
    assert malformed.raw["savings_pct"] == 0.0


def test_itad_price_normalization_preserves_best_deal_and_history() -> None:
    deal = _best_deal_summary([
        {
            "price": {"amount": 15, "currency": "usd"},
            "regular": {"amount": 30},
            "cut": 50,
            "shop": {"name": "Store A"},
        },
        {
            "price": {"amount": 10, "currency": "eur"},
            "regular": {"amount": 40},
            "cut": 75,
            "shop": {"name": "Store B"},
        },
    ])
    low, recorded = _history_low({
        "price": {"amount": 7.5},
        "recorded": "2026-01-12T08:30:00+00:00",
    })

    assert deal.store == "Store B"
    assert deal.currency == "EUR"
    assert deal.list_price == 40
    assert deal.sale_price == 10
    assert deal.discount_percent == 75
    assert low == 7.5
    assert recorded is not None and recorded.isoformat() == "2026-01-12"


def test_steam_normalization_keeps_metadata_groups_separate() -> None:
    normalized = SteamService()._normalize(620, {
        "name": "Portal 2",
        "platforms": {"windows": True, "mac": True, "linux": False},
        "developers": ["Valve"],
        "publishers": ["Valve"],
        "genres": [{"description": "Puzzle"}],
        "categories": [{"description": "Single-player"}],
        "screenshots": [{"path_full": "https://example.test/portal.jpg"}],
        "pc_requirements": {"minimum": "CPU: Test", "recommended": "GPU: Test"},
        "dlc": [123, "456", "invalid"],
    })

    assert normalized.platforms == ["PC", "macOS"]
    assert normalized.genres == ["Puzzle"]
    assert normalized.developer == "Valve"
    assert normalized.publisher == "Valve"
    assert normalized.raw["categories"] == ["Single-player"]
    assert normalized.raw["screenshots"] == ["https://example.test/portal.jpg"]
    assert normalized.raw["dlc_ids"] == [123, 456]


def test_normalized_game_rejects_numeric_invariant_violations() -> None:
    with pytest.raises(ValueError):
        NormalizedGame(source="provider", external_id="1", name="Game", score=float("nan"))
    with pytest.raises(ValueError):
        NormalizedGame(source="provider", external_id="1", name="Game", sale_price=-0.01)
