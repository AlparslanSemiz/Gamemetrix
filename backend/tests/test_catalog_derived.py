"""Stored catalog columns: pure derivation, ORM upkeep, and parity with the migration backfill."""

import importlib.util
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm.attributes import flag_modified

from app.integrations.sync.ranking import compute_rank_fields
from app.models import Game
from app.services import game_query
from app.services.catalog_derived import DERIVED_FIELDS, derive_catalog_columns
from app.services.steam_id_audit import purge_wrong_app_data

from .pg_support import make_game, pg_session, requires_postgres  # noqa: F401

pytestmark = requires_postgres


def _row(source: str, score, reviews=0, status="live") -> dict:
    return {"source": source, "score": score, "review_count": reviews, "status": status}


def test_derivation_rules() -> None:
    values = derive_catalog_columns(
        [
            _row("Metacritic", 88, 40),
            _row("OpenCritic", 91.5, 12),
            _row("Steam", 80, 5000),
            _row("IGDB", 70, 3, status="stale"),
            _row("RAWG", 4, 100),
            _row("Steam", 0, 7),
            {"source": "Metacritic", "score": "x", "review_count": -4},
            "garbage",
        ],
        ["PC", " PlayStation 5 "],
        ["Multiplayer", "Splitscreen"],
        ["Co-op", "RPG"],
    )
    assert values["review_count_total"] == 40 + 12 + 5000 + 3 + 100 + 7
    assert values["live_review_count"] == 40 + 12 + 5000 + 100  # RAWG is live too (any source counts)
    assert values["live_primary_sources"] == 3
    assert values["has_live_critic"] is True
    assert (values["metacritic_live_score"], values["opencritic_score"], values["steam_score"]) == (88, 91.5, 80)
    assert values["platform_tags"] == ["pc", "playstation", "playstation 5", "steam"]
    assert values["mode_tags"] == ["coop", "multiplayer"]


def test_steam_needs_a_pc_platform_to_count_as_live_primary() -> None:
    rows = [_row("Steam", 80, 10), _row("Metacritic", 90, 10)]
    assert derive_catalog_columns(rows, ["PlayStation 5"])["live_primary_sources"] == 1
    assert derive_catalog_columns(rows, ["Microsoft Windows"])["live_primary_sources"] == 2


def test_columns_follow_source_scores(pg_session) -> None:
    game = make_game("Stored", source_scores=[_row("Steam", 80, 100)])
    pg_session.add(game)
    pg_session.commit()
    assert (game.steam_score, game.live_review_count, game.has_live_critic) == (80, 100, False)

    game.source_scores = [_row("Steam", 80, 100), _row("Metacritic", 90, 50)]
    game.metrix_score = 85.0
    game.rank_score, game.is_rankable, _ = compute_rank_fields(game)
    pg_session.commit()
    pg_session.expire_all()
    stored = pg_session.get(Game, game.id)
    assert (stored.metacritic_live_score, stored.review_count_total, stored.has_live_critic) == (90, 150, True)
    assert stored.live_primary_sources == 2

    # In-place edits flagged the SQLAlchemy way are picked up too.
    stored.source_scores[1]["status"] = "stale"
    flag_modified(stored, "source_scores")
    pg_session.commit()
    assert pg_session.get(Game, game.id).has_live_critic is False

    stored.platforms = ["Linux"]
    pg_session.commit()
    assert pg_session.get(Game, game.id).platform_tags == ["linux"]


def test_steam_audit_purge_updates_columns(pg_session) -> None:
    game = make_game("Wrong app", source_scores=[_row("Steam", 90, 1000), _row("Metacritic", 80, 10)])
    pg_session.add(game)
    pg_session.commit()
    assert game.steam_score == 90

    purge_wrong_app_data(pg_session, game)
    pg_session.commit()
    pg_session.refresh(game)
    assert (game.steam_score, game.review_count_total, game.live_primary_sources) == (0, 10, 1)


def test_backfill_sql_matches_python(pg_session) -> None:
    spec = importlib.util.spec_from_file_location(
        "migration_0022",
        Path(__file__).resolve().parents[1] / "alembic/versions/20261119_0022_catalog_stored_columns.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    cases = [
        ([_row("Steam", 80, 100), _row("Metacritic", 90, 50), _row("OpenCritic", 85.5, 7)], ["PC", "PlayStation 5"], ["Multiplayer"], ["Co-op"]),
        ([_row("Steam", 80, 100)], ["Nintendo Switch"], [], ["MMORPG", "Single Player"]),
        ([_row("IGDB", 70, 3, status="stale"), _row("RAWG", 4, 5_000_000_000), _row("Steam", 101, 9)], ["Wii U", "Xbox One"], ["coop"], []),
        ([_row("Metacritic", "88", 2), {"source": "Metacritic", "score": 70, "review_count": 12.9}, "junk", 7], [" Steam ", "Linux", 5], ["singleplayer", "x"], ["PvP"]),
        ([], [], [], []),
    ]
    for index, (scores, platforms, modes, genres) in enumerate(cases):
        pg_session.add(make_game(f"Case {index}", source_scores=scores, platforms=platforms, game_modes=modes, genres=genres))
    pg_session.commit()

    zeros = ", ".join(f"{name} = {'ARRAY[]::text[]' if name.endswith('tags') else ('false' if name == 'has_live_critic' else '0')}" for name in DERIVED_FIELDS)
    pg_session.execute(text(f"UPDATE games SET {zeros}"))
    pg_session.execute(text(migration.BACKFILL_SQL))
    pg_session.commit()
    pg_session.expire_all()

    for game in pg_session.scalars(select(Game).order_by(Game.id)):
        expected = derive_catalog_columns(game.source_scores, game.platforms, game.game_modes, game.genres)
        actual = {name: getattr(game, name) for name in DERIVED_FIELDS}
        assert actual == expected, game.title


def test_query_filters_and_sorts_use_stored_columns(pg_session) -> None:
    pg_session.add_all([
        make_game("A", source_scores=[_row("Metacritic", 90, 10), _row("Steam", 80, 900)], platforms=["PC"], game_modes=["coop"]),
        make_game("B", source_scores=[_row("Steam", 70, 5000)], platforms=["PlayStation 5"], genres=["Single Player"]),
        make_game("C", source_scores=[], platforms=["Xbox One"]),
    ])
    pg_session.commit()

    def titles(statement) -> list[str]:
        return [g.title for g in pg_session.scalars(statement)]

    base = select(Game)
    assert titles(game_query.apply_sort(base, "review_count", "desc"))[:2] == ["B", "A"]
    assert titles(game_query.apply_sort(base, "steam_score", "desc"))[:2] == ["A", "B"]
    assert titles(game_query.apply_sort(base, "metacritic_score", "desc"))[0] == "A"
    filtered = lambda **kw: sorted(titles(game_query.apply_advanced_filters(base, game_query.CatalogFilters(**kw))))
    assert filtered(min_live_sources=2) == ["A"]
    assert filtered(require_critic=True) == ["A"]
    assert filtered(min_ratings=1000) == ["B"]
    assert filtered(platform="Steam") == ["A"]
    assert filtered(platform="PlayStation") == ["B"]
    assert filtered(platform="xbox") == ["C"]
    assert filtered(player_mode="coop") == ["A"]
    assert filtered(player_mode="singleplayer") == ["B"]
