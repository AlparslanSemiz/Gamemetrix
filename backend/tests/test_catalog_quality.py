from datetime import UTC, date, datetime

import pytest

from app.integrations.types import NormalizedGame
from app.models import Game
from app.services.catalog_quality import (
    catalog_quality_signals,
    parse_quality_verdict,
)
from app.services.catalog_quality.remediation import (
    ResearchedGame,
    apply_repair_plan,
    build_repair_plan,
    repair_fields,
    restore_repair,
)
from app.services.catalog_quality import research as research_module
from app.services.catalog_quality import batch as quality_batch_module
from app.services.catalog_quality.review import QualityVerdict
from app.services.metadata import clean_game_summary


def _game(**overrides: object) -> Game:
    values: dict[str, object] = {
        "id": 1,
        "title": "Portal 2",
        "slug": "portal-2",
        "summary": "Portal 2 is a first-person puzzle game built around portals, physics, and cooperative problem solving.",
        "cover_url": "https://example.com/portal-2.jpg",
        "release_date": date(2011, 4, 18),
        "release_year": 2011,
        "metrix_score": 95.0,
        "rank_score": 95.0,
        "critic_score": 95.0,
        "user_score": 95.0,
        "genres": ["Puzzle"],
        "platforms": ["PC"],
        "source_scores": [],
        "content_type": "game",
        "screenshots": [],
        "system_requirements": [],
        "dlcs": [],
        "similar_games": [],
    }
    values.update(overrides)
    return Game(**values)


def test_quality_signals_detect_bad_title_summary_and_metadata() -> None:
    game = _game(
        title="b",
        summary="<h3>About</h3>b is part of the imported catalog.",
        release_date=date(1970, 1, 1),
        release_year=1970,
        genres=["Uncategorized"],
        platforms=["Unknown"],
        developer=None,
    )

    signals = catalog_quality_signals(game)

    assert "suspicious_title" in signals
    assert "raw_html_summary" in signals
    assert "missing_core_metadata" in signals
    assert "unknown_release_with_weak_metadata" in signals


def test_quality_signals_send_shared_summaries_for_semantic_review() -> None:
    game = _game()

    signals = catalog_quality_signals(game, ("Unrelated Game",))

    assert signals == ["summary_shared_with_other_titles"]


def test_missing_developer_alone_does_not_trigger_ai_review() -> None:
    game = _game(developer=None)

    assert catalog_quality_signals(game) == []


def test_missing_summary_alone_does_not_spend_an_ai_review() -> None:
    game = _game(summary="")

    assert catalog_quality_signals(game) == []


def test_quality_scan_has_a_bounded_orm_window() -> None:
    assert quality_batch_module._MAX_SCAN_ROWS <= 200


def test_ai_quality_verdict_is_advisory_until_an_admin_decides() -> None:
    class _Session:
        def __init__(self) -> None:
            self.added: list[object] = []

        def add(self, value: object) -> None:
            self.added.append(value)

    game = _game(content_type="game", data_complete=True)
    db = _Session()

    outcome = quality_batch_module._apply_verdict(
        db,
        game,
        None,
        ["non_game_marker"],
        QualityVerdict("NOT_GAME", ("content_type",), "Looks like downloadable content."),
    )

    review = db.added[0]
    assert outcome == "needs_review"
    assert game.content_type == "game"
    assert game.data_complete is True
    assert review.status == "needs_review"
    assert "ai:verdict:not_game" in review.signals


@pytest.mark.asyncio
async def test_catalog_repair_does_not_search_rawg_without_a_trusted_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_search(*_args, **_kwargs):
        pytest.fail("catalog repair must not spend RAWG on an unverified title search")

    monkeypatch.setattr(
        research_module.rawg_service,
        "is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        research_module.rawg_service,
        "search_game",
        unexpected_search,
    )

    assert await research_module._research_rawg(_game(), None, True) is None


def test_parse_quality_verdict_accepts_fenced_json_and_filters_fields() -> None:
    verdict = parse_quality_verdict(
        '```json\n{"verdict":"bad_metadata","fields":["summary","secret","summary"],'
        '"reason":"The description belongs to a different game."}\n```'
    )

    assert verdict is not None
    assert verdict.verdict == "BAD_METADATA"
    assert verdict.fields == ("summary",)
    assert verdict.reason == "The description belongs to a different game."


def test_parse_quality_verdict_rejects_unstructured_or_unknown_answers() -> None:
    assert parse_quality_verdict("This looks wrong") is None
    assert parse_quality_verdict('{"verdict":"DELETE","fields":[],"reason":"no"}') is None


def _researched(
    source: str,
    *,
    name: str = "Portal 2",
    summary: str | None = None,
    trusted: bool = True,
) -> ResearchedGame:
    return ResearchedGame(
        record=NormalizedGame(
            source=source,
            external_id=f"{source.lower()}-portal-2",
            name=name,
            release_date=date(2011, 4, 18),
            genres=["Puzzle"],
            platforms=["PC"],
            developer="Valve",
            publisher="Valve",
            summary=summary,
        ),
        trusted_identity=trusted,
    )


def test_repair_fields_are_derived_from_ai_and_deterministic_signals() -> None:
    assert repair_fields(
        [
            "suspicious_title",
            "summary_shared_with_other_titles",
            "unknown_release_with_weak_metadata",
            "ai:summary",
        ]
    ) == {"title", "summary", "release_year"}


def test_repair_plan_overwrites_a_wrong_nonempty_summary_from_trusted_metadata() -> None:
    game = _game(
        summary="The action of Ryse: Son of Rome is set in the capital of the Roman Empire.",
    )
    records = [
        _researched(
            "IGDB",
            summary=(
                "Portal 2 is a first-person puzzle game in which Chell and GLaDOS "
                "return to Aperture Science for a new series of portal experiments."
            ),
        )
    ]

    plan = build_repair_plan(game, ["ai:summary"], records)

    assert plan.changes["summary"].startswith("Portal 2 is a first-person puzzle game")
    assert plan.sources == {"summary": "IGDB"}


def test_bad_title_requires_two_provider_identity_consensus() -> None:
    game = _game(title="b", slug="b")
    single_source = [_researched("Steam", name="BattleBlock Theater")]

    assert build_repair_plan(game, ["ai:title"], single_source).changes == {}

    consensus = [
        _researched("Steam", name="BattleBlock Theater"),
        _researched("IGDB", name="BattleBlock Theater"),
    ]
    plan = build_repair_plan(game, ["ai:title"], consensus)

    assert plan.changes == {"title": "BattleBlock Theater"}
    assert plan.sources == {"title": "IGDB"}


def test_valid_title_never_accepts_consensus_for_another_game() -> None:
    game = _game()
    wrong_records = [
        _researched("Steam", name="Ryse: Son of Rome", summary="A Roman action game."),
        _researched("IGDB", name="Ryse: Son of Rome", summary="A Roman action game."),
    ]

    plan = build_repair_plan(game, ["ai:summary"], wrong_records)

    assert plan.changes == {}


def test_repair_application_is_reversible_until_post_verification() -> None:
    game = _game(
        summary="Wrong summary that belongs to another game and must not survive verification.",
        summary_short="Wrong short summary.",
        data_complete=True,
    )
    plan = build_repair_plan(
        game,
        ["ai:summary"],
        [
            _researched(
                "IGDB",
                summary=(
                    "Portal 2 is a first-person puzzle game about portals, physics, "
                    "robots, and escaping the ruined Aperture Science facility."
                ),
            )
        ],
    )
    original_summary = game.summary

    snapshot = apply_repair_plan(game, plan, datetime.now(UTC))

    assert game.summary != original_summary
    assert game.summary_short is None
    assert game.data_complete is False

    restore_repair(game, snapshot)

    assert game.summary == original_summary
    assert game.summary_short == "Wrong short summary."
    assert game.data_complete is True


def test_summary_cleaner_removes_provider_html_before_storage() -> None:
    cleaned = clean_game_summary(
        "<h3>About</h3><p>Portal 2 is a puzzle game about portals, physics, "
        "robots, and escaping a ruined scientific facility.</p>",
        "Portal 2",
    )

    assert cleaned is not None
    assert "<h3>" not in cleaned
    assert "<p>" not in cleaned
