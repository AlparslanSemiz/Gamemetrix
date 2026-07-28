from app.services.steam_system_requirements_backfill import (
    _identity_matches,
    _requirements_from_raw,
)


def test_requirement_rows_keep_published_legacy_hardware() -> None:
    rows = [{
        "platform": "PC",
        "minimum": "OS: Windows XP\nMemory: 256MB RAM",
        "recommended": "",
    }]

    assert _requirements_from_raw(rows) == rows


def test_requirement_rows_require_a_nonempty_pc_entry() -> None:
    assert _requirements_from_raw([{
        "platform": "Linux",
        "minimum": "OS: Ubuntu 22.04",
        "recommended": "",
    }]) == []
    assert _requirements_from_raw([{
        "platform": "PC",
        "minimum": "",
        "recommended": "",
    }]) == []


def test_requirement_identity_check_rejects_wrong_steam_app() -> None:
    assert _identity_matches("Portal 2", "Portal 2") is True
    assert _identity_matches("Portal 2", "Counter-Strike") is False
    assert _identity_matches(
        "Resident Evil 4 Remake",
        "Resident Evil 4",
        game_year=2023,
        provider_year=2023,
    ) is True
