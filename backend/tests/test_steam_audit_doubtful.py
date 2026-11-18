"""Same name but years apart: keep the id and ask a human instead of clearing it."""

from types import SimpleNamespace

from app.integrations.steam.client import AppdetailsOutcome
from app.services.steam_id_audit import judge


def _game(title: str, year: int) -> SimpleNamespace:
    return SimpleNamespace(title=title, release_year=year)


def _outcome(name: str, date: str) -> AppdetailsOutcome:
    return AppdetailsOutcome("ok", {"type": "game", "name": name, "release_date": {"date": date}})


def test_late_port_with_same_name_is_doubtful_not_mismatch() -> None:
    verdict, reason, _ = judge(_game("The Last of Us Part I", 2013), _outcome("The Last of Us™ Part I", "28 Mar, 2023"))
    assert (verdict, reason) == ("doubtful", "year_mismatch")
    verdict, _, _ = judge(_game("POSTAL 2", 2003), _outcome("POSTAL 2", "13 Apr, 2012"))
    assert verdict == "doubtful"


def test_explicit_year_conflict_stays_a_mismatch() -> None:
    verdict, reason, _ = judge(
        _game("Call of Duty: Modern Warfare II", 2022),
        _outcome("Call of Duty®: Modern Warfare® 2 (2009)", "11 Nov, 2009"),
    )
    assert verdict == "mismatch"
    assert reason == "year_mismatch"


def test_different_name_is_still_a_mismatch() -> None:
    verdict, reason, _ = judge(_game("Elden Ring", 2022), _outcome("ELDEN RING NIGHTREIGN", "30 May, 2025"))
    assert (verdict, reason) == ("mismatch", "name_mismatch")


def test_our_explicit_year_conflict_stays_a_mismatch() -> None:
    verdict, _, _ = judge(
        _game("Call of Duty: Modern Warfare 3 (2011)", 2011),
        _outcome("Call of Duty®: Modern Warfare® III", "10 Nov, 2023"),
    )
    assert verdict == "mismatch"
