from datetime import date

import pytest

from app.models import Game
from app.services.metadata import (
    UNUSABLE_SUMMARY_QUALITY,
    invalidate_summary_audit,
    summary_needs_enrichment,
)
from app.services.summarizer import ai as ai_module
from app.services.summarizer import batch as batch_module
from app.services.summarizer.ai import (
    REJECTED_VERDICT,
    audit_description,
    parse_audit_answer,
    shorten_summary,
)
from app.services.summarizer.issues import (
    describe_issues,
    needs_ai_review,
    sanitize_description,
)


_CLEAN_SUMMARY = (
    "Hollow Knight is a hand-drawn metroidvania set in the ruined insect kingdom of "
    "Hallownest. Players explore interconnected caverns, master a precise melee combat "
    "system, and unlock movement abilities that open earlier areas. The tone is quiet "
    "and melancholic, told through environmental detail rather than dialogue."
)


def _game(**overrides: object) -> Game:
    values: dict[str, object] = {
        "id": 1,
        "title": "Hollow Knight",
        "slug": "hollow-knight",
        "summary": _CLEAN_SUMMARY,
        "cover_url": "https://example.com/hk.jpg",
        "release_date": date(2017, 2, 24),
        "release_year": 2017,
        "metrix_score": 90.0,
        "rank_score": 90.0,
        "critic_score": 90.0,
        "user_score": 90.0,
        "genres": ["Metroidvania"],
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


class _Scalars:
    def __init__(self, rows: list[Game]) -> None:
        self._rows = rows

    def all(self) -> list[Game]:
        return self._rows


class _Session:
    """Minimal stand-in for the ORM session the batch uses."""

    def __init__(self, rows: list[Game]) -> None:
        self._rows = rows
        self.commits = 0

    def scalars(self, _statement: object) -> _Scalars:
        return _Scalars(self._rows)

    def add(self, _instance: object) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1


# ── deterministic detection ──────────────────────────────────────────────────

def test_a_good_description_has_no_issues() -> None:
    assert describe_issues(_CLEAN_SUMMARY) == []


def test_issues_cover_markup_encoding_promo_and_links() -> None:
    issues = describe_issues(
        "<p>Hollow Knightâ€™s world awaits.</p> Wishlist it now! "
        "Read more at https://example.com/store."
    )

    assert {"markup", "encoding", "promo", "boilerplate"} <= set(issues)


def test_issues_flag_length_language_and_repetition() -> None:
    assert "too_short" in describe_issues("A game.")
    assert "too_long" in describe_issues("An excellent action game. " * 40)
    assert "non_english" in describe_issues(
        "これは日本語で書かれた説明文であり、英語の説明ではありません。プレイヤーは広大な世界を探索します。"
    )
    assert "duplicate_sentences" in describe_issues(
        "It is an action game about exploring ruins. "
        "It is an action game about exploring ruins. "
        "Players fight bosses in large underground arenas."
    )
    assert "shouting" in describe_issues(
        "THIS IS THE GREATEST ADVENTURE GAME EVER MADE AND YOU SHOULD PLAY IT RIGHT NOW."
    )


def test_generated_placeholder_text_is_reported_alone_and_never_reaches_ai() -> None:
    issues = describe_issues("Hollow Knight is part of the imported RAWG catalog.")

    assert issues == ["placeholder"]
    assert needs_ai_review(issues) is False


def test_empty_text_is_reported_alone_and_never_reaches_ai() -> None:
    assert describe_issues("   ") == ["empty"]
    assert needs_ai_review(["empty"]) is False


def test_any_remaining_issue_after_sanitizing_escalates_to_ai() -> None:
    assert needs_ai_review(["promo"]) is True
    assert needs_ai_review(["non_english"]) is True
    assert needs_ai_review([]) is False


# ── mechanical repair ────────────────────────────────────────────────────────

def test_sanitizer_removes_markup_promo_links_and_repeats() -> None:
    messy = (
        "<h3>About</h3><p>Hollow Knight is a hand-drawn metroidvania set in the ruined "
        "insect kingdom of Hallownest.</p> Hollow Knight is a hand-drawn metroidvania set "
        "in the ruined insect kingdom of Hallownest. Wishlist it now! "
        "Read more at https://example.com."
    )


    cleaned = sanitize_description(messy)

    assert cleaned == (
        "Hollow Knight is a hand-drawn metroidvania set in the ruined insect "
        "kingdom of Hallownest."
    )
    assert describe_issues(cleaned) == []


def test_sanitizer_repairs_mojibake() -> None:
    cleaned = sanitize_description(
        "Hollow Knightâ€™s ruined kingdom rewards careful exploration and precise "
        "combat across its interconnected caverns."
    )

    assert "â€™" not in cleaned
    assert "encoding" not in describe_issues(cleaned)


# ── AI response handling ─────────────────────────────────────────────────────

def test_audit_answer_parsing_is_strict() -> None:
    assert parse_audit_answer('{"verdict":"OK","summary":"","reason":"fine"}').verdict == "OK"
    assert parse_audit_answer('Here you go: {"verdict":"UNUSABLE","summary":""}').verdict == "UNUSABLE"
    assert parse_audit_answer('{"verdict":"MAYBE","summary":""}') is None
    assert parse_audit_answer("not json at all") is None
    assert parse_audit_answer(None) is None


def _stub_groq(monkeypatch: pytest.MonkeyPatch, answer: str | None) -> list[str]:
    prompts: list[str] = []

    async def fake_generate(_system: str, user: str, **_kwargs: object) -> str | None:
        prompts.append(user)
        return answer

    monkeypatch.setattr(ai_module, "generate_text", fake_generate)
    return prompts


@pytest.mark.asyncio
async def test_a_faithful_rewrite_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_groq(
        monkeypatch,
        '{"verdict":"CLEANED","summary":"Hollow Knight is a hand-drawn metroidvania '
        'set in the ruined insect kingdom of Hallownest. Players explore its caverns '
        'and fight with a precise melee system.","reason":"removed store text"}',
    )

    verdict = await audit_description("Hollow Knight", _CLEAN_SUMMARY, ["promo"])

    assert verdict is not None
    assert verdict.verdict == "CLEANED"
    assert verdict.summary.startswith("Hollow Knight is a hand-drawn metroidvania")


@pytest.mark.asyncio
async def test_a_rewrite_sharing_no_vocabulary_with_the_source_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_groq(
        monkeypatch,
        '{"verdict":"CLEANED","summary":"Competitors pilot armoured mechs through '
        'orbital stations, upgrading railguns between deployments while rival '
        'corporations bid for salvage rights across the asteroid belt.","reason":"x"}',
    )

    verdict = await audit_description("Hollow Knight", _CLEAN_SUMMARY, ["promo"])

    assert verdict is not None
    assert verdict.verdict == REJECTED_VERDICT
    assert verdict.summary == ""


@pytest.mark.asyncio
async def test_a_rewrite_that_reintroduces_issues_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_groq(
        monkeypatch,
        '{"verdict":"CLEANED","summary":"<p>Hollow Knight is a hand-drawn '
        'metroidvania set in the ruined insect kingdom of Hallownest with precise '
        'combat.</p>","reason":"x"}',
    )

    verdict = await audit_description("Hollow Knight", _CLEAN_SUMMARY, ["promo"])

    assert verdict is not None
    assert verdict.verdict == REJECTED_VERDICT


@pytest.mark.asyncio
async def test_a_translation_is_accepted_despite_sharing_no_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_groq(
        monkeypatch,
        '{"verdict":"CLEANED","summary":"Players explore a vast underground world, '
        'defeating bosses and unlocking new movement abilities as they uncover the '
        'history of a fallen kingdom.","reason":"translated"}',
    )
    japanese = "これは日本語で書かれた説明文であり、英語の説明ではありません。プレイヤーは広大な世界を探索します。"

    verdict = await audit_description("Hollow Knight", japanese, ["non_english"])

    assert verdict is not None
    assert verdict.verdict == "CLEANED"


@pytest.mark.asyncio
async def test_no_answer_from_groq_yields_no_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_groq(monkeypatch, None)

    assert await audit_description("Hollow Knight", _CLEAN_SUMMARY, ["promo"]) is None


@pytest.mark.asyncio
async def test_provider_text_is_bounded_before_it_reaches_groq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts = _stub_groq(monkeypatch, '{"verdict":"OK","summary":"","reason":""}')

    await audit_description("Long Game", "x" * 10_000, ["too_long"])

    assert len(prompts[0]) <= 2_200


@pytest.mark.asyncio
async def test_short_summary_rejects_links_markup_and_ungrounded_calls_to_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_groq(
        monkeypatch,
        "<a href='https://evil.example'>Buy this unrelated product now</a>",
    )

    shortened = await shorten_summary("Hollow Knight", _CLEAN_SUMMARY)

    assert "evil.example" not in shortened
    assert "<a" not in shortened
    assert shortened == ai_module.extract_short_summary(_CLEAN_SUMMARY)


# ── batch behaviour ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_repairs_mechanically_with_no_ai_budget_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*_args: object, **_kwargs: object) -> None:
        pytest.fail("mechanical repair must not cost an AI call")

    monkeypatch.setattr(batch_module, "audit_description", fail)
    monkeypatch.setattr(batch_module, "shorten_summary", fail)
    game = _game(
        summary=f"<h3>About</h3><p>{_CLEAN_SUMMARY}</p>",
        summary_short="already there",
    )
    db = _Session([game])

    counts = await batch_module.refresh_summary_batch(db, limit=10, ai_limit=0)

    assert game.summary == _CLEAN_SUMMARY
    assert counts["sanitized"] == 1
    assert counts["ai_checked"] == 0
    assert game.summary_quality == batch_module.CLEANED_SUMMARY_QUALITY
    assert game.summary_checked_at is not None
    assert game.summary_refreshed_at is not None


@pytest.mark.asyncio
async def test_a_clean_but_never_audited_description_still_gets_an_ai_opinion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def audit(_title: str, _text: str, _issues: list[str]):
        return ai_module.DescriptionVerdict("OK", "", "reads fine")

    monkeypatch.setattr(batch_module, "audit_description", audit)
    game = _game(summary_short="already there")
    db = _Session([game])

    counts = await batch_module.refresh_summary_batch(db, limit=10, ai_limit=5)

    assert counts["ok"] == 1
    assert game.summary == _CLEAN_SUMMARY
    assert game.summary_quality == batch_module.OK_SUMMARY_QUALITY
    # An unchanged description must not look freshly rewritten to other jobs.
    assert game.summary_refreshed_at is None


@pytest.mark.asyncio
async def test_batch_marks_placeholder_text_unusable_for_provider_re_enrichment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*_args: object, **_kwargs: object) -> None:
        pytest.fail("placeholder text must not reach the AI")

    monkeypatch.setattr(batch_module, "audit_description", fail)
    monkeypatch.setattr(batch_module, "shorten_summary", fail)
    game = _game(
        summary="Hollow Knight is part of the imported RAWG catalog.",
        summary_short="already there",
    )
    db = _Session([game])

    counts = await batch_module.refresh_summary_batch(db, limit=10, ai_limit=5)

    assert counts["unusable"] == 1
    assert game.summary_quality == UNUSABLE_SUMMARY_QUALITY
    assert summary_needs_enrichment(game) is True


def test_replacing_a_summary_clears_a_stale_unusable_verdict() -> None:
    game = _game(
        summary="Hollow Knight is part of the imported RAWG catalog.",
        summary_quality=UNUSABLE_SUMMARY_QUALITY,
        summary_short="stale blurb",
    )
    assert summary_needs_enrichment(game) is True

    game.summary = _CLEAN_SUMMARY
    invalidate_summary_audit(game)

    # Without this the row would stay queued for provider re-enrichment forever.
    assert summary_needs_enrichment(game) is False
    assert game.summary_short is None
    assert game.summary_checked_at is None


@pytest.mark.asyncio
async def test_batch_never_exceeds_its_ai_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def audit(title: str, _text: str, _issues: list[str]) -> None:
        calls.append(title)
        return None

    monkeypatch.setattr(batch_module, "audit_description", audit)
    games = [
        _game(id=index, slug=f"game-{index}", summary=f"{_CLEAN_SUMMARY} Wishlist it now!")
        for index in range(5)
    ]
    db = _Session(games)

    counts = await batch_module.refresh_summary_batch(db, limit=10, ai_limit=2)

    # The first unanswered call stops further escalation for the whole batch.
    assert len(calls) == 1
    assert counts["unavailable"] == 1
    assert counts["processed"] == 5


@pytest.mark.asyncio
async def test_display_blurb_is_still_produced_without_any_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*_args: object, **_kwargs: object) -> None:
        pytest.fail("no AI call is allowed once the batch budget is spent")

    monkeypatch.setattr(batch_module, "audit_description", fail)
    monkeypatch.setattr(batch_module, "shorten_summary", fail)
    game = _game(summary_short=None)
    db = _Session([game])

    counts = await batch_module.refresh_summary_batch(db, limit=10, ai_limit=0)

    assert counts["shortened"] == 1
    assert game.summary_short
    assert game.summary_short.startswith("Hollow Knight is a hand-drawn metroidvania")
    assert len(game.summary_short) <= 450


@pytest.mark.asyncio
async def test_batch_prefers_flagged_rows_over_never_audited_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    async def audit(title: str, _text: str, _issues: list[str]):
        seen.append(title)
        return ai_module.DescriptionVerdict("OK", "", "")

    monkeypatch.setattr(batch_module, "audit_description", audit)
    monkeypatch.setattr(batch_module, "shorten_summary", audit)
    clean = _game(id=1, slug="clean", title="Clean", summary_short="x")
    flagged = _game(
        id=2,
        slug="flagged",
        title="Flagged",
        summary=f"{_CLEAN_SUMMARY} これは日本語の文章です。",
        summary_short="x",
    )
    db = _Session([clean, flagged])

    await batch_module.refresh_summary_batch(db, limit=10, ai_limit=1)

    assert seen == ["Flagged"]
