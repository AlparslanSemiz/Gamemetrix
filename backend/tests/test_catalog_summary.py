from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.routers.games import catalog_summary
from app.schemas import GameSlugBatchRequest


class _ScalarRows:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self._rows


class _BatchSession:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    def scalars(self, _statement) -> _ScalarRows:
        return _ScalarRows(self.rows)


def _catalog_game(slug: str, game_id: int, *, with_price: bool = False) -> SimpleNamespace:
    prices = []
    if with_price:
        prices.append(SimpleNamespace(
            source="itad",
            store="Steam",
            platform="PC",
            region="US",
            currency="USD",
            list_price=29.99,
            sale_price=14.99,
            discount_percent=50,
            historical_low=12.99,
            historical_low_date=date(2026, 7, 1),
            sale_end_date=None,
            is_free=False,
            is_subscription_included=False,
            subscription_service=None,
            url="https://example.test/deal",
            fetched_at=datetime.now(UTC),
        ))
    return SimpleNamespace(
        id=game_id,
        title=slug.replace("-", " ").title(),
        slug=slug,
        summary_short="Short card summary.",
        cover_url="https://example.test/cover.jpg",
        release_date=date(2025, 1, 1),
        release_year=2025,
        metrix_score=88.0,
        genres=["RPG"],
        platforms=["PC"],
        source_scores=[],
        price_snapshots=prices,
    )


def test_catalog_batch_preserves_input_order_and_omits_unknown_slugs(monkeypatch) -> None:
    requested_price_modes: list[bool] = []
    monkeypatch.setattr(
        catalog_summary,
        "catalog_load_options",
        lambda *, include_prices: requested_price_modes.append(include_prices) or (),
    )
    db = _BatchSession([
        _catalog_game("second-game", 2),
        _catalog_game("first-game", 1),
    ])

    response = catalog_summary.catalog_games_by_slug.__wrapped__(
        request=SimpleNamespace(),
        payload=GameSlugBatchRequest(
            slugs=["first-game", "unknown-game", "second-game"],
        ),
        include_prices=False,
        db=db,
    )

    assert [game.slug for game in response.games] == ["first-game", "second-game"]
    assert response.total == 2
    assert requested_price_modes == [False]
    assert all(game.price_snapshots == [] for game in response.games)


def test_catalog_batch_loads_prices_only_when_requested(monkeypatch) -> None:
    requested_price_modes: list[bool] = []
    monkeypatch.setattr(
        catalog_summary,
        "catalog_load_options",
        lambda *, include_prices: requested_price_modes.append(include_prices) or (),
    )
    db = _BatchSession([_catalog_game("priced-game", 3, with_price=True)])

    response = catalog_summary.catalog_games_by_slug.__wrapped__(
        request=SimpleNamespace(),
        payload=GameSlugBatchRequest(slugs=["priced-game"]),
        include_prices=True,
        db=db,
    )

    assert requested_price_modes == [True]
    assert response.games[0].price_snapshots[0].discount_percent == 50
