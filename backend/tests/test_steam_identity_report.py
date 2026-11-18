"""The 43 non-verified findings (42 mismatch + 1 reclassified) of the 300-game verify_steam_ids dry run, as fixtures.

Catalog and Steam years are the real release years; `reason` is the expected verdict
(`ok` = the same product, anything else = the audit must still flag it).
"""

import pytest

from app.integrations.steam.identity import steam_identity_verdict

# (title, catalog year, steam name, steam year, steam type, expected reason)
CASES = [
    ("Elden Ring", 2022, "ELDEN RING NIGHTREIGN", 2025, "game", "name_mismatch"),
    ("The Witcher 3: Wild Hunt", 2015, "The Witcher 3: Wild Hunt — Remastered", 2015, "game", "ok"),
    ("Civilization VI", 2016, "Sid Meier’s Civilization® VI", 2016, "game", "ok"),
    ("God of War (2018)", 2018, "God of War", 2022, "game", "ok"),
    ("The Last of Us Part I", 2022, "The Last of Us™ Part I", 2023, "game", "ok"),
    ("Persona 5 Royal", 2019, "Persona 5 Royal", 2022, "game", "ok"),
    ("Yakuza 0", 2015, "Yakuza 0", 2018, "game", "ok"),
    ("Titanfall 2", 2016, "Titanfall® 2", 2016, "game", "ok"),
    ("Resident Evil 4 Remake", 2023, "Resident Evil 4", 2023, "game", "ok"),
    ("Resident Evil 4", 2005, "Resident Evil 4 (2005)", 2007, "game", "ok"),
    ("Resident Evil 2 Remake", 2019, "Resident Evil 2", 2019, "game", "ok"),
    ("Dragon Age: Inquisition", 2014, "Dragon Age™ Inquisition", 2014, "game", "ok"),
    ("Into the Breach", 2018, "SCP – Containment Breach", 2025, "game", "name_mismatch"),
    ("Slay the Spire", 2019, "Slay the Spire 2", 2026, "game", "name_mismatch"),
    ("Pathfinder: Wrath of the Righteous", 2021, "Pathfinder: Wrath of the Righteous - Enhanced Edition", 2021, "game", "ok"),
    ("Spiritfarer", 2020, "Spiritfarer®: Farewell Edition", 2020, "game", "ok"),
    ("Sea of Stars", 2023, "Sea of Stars: Sunset Edition", 2023, "game", "ok"),
    ("Darkest Dungeon", 2016, "Darkest Dungeon® II", 2023, "game", "name_mismatch"),
    ("Age of Empires IV", 2021, "Age of Empires IV: Anniversary Edition", 2021, "game", "ok"),
    ("Call of Duty: Modern Warfare II", 2022, "Call of Duty®: Modern Warfare® 2 (2009)", 2009, "game", "year_mismatch"),
    ("New World: Aeternum", 2021, "New World Playtest", 2021, "game", "name_mismatch"),
    ("Path of Exile", 2013, "Path of Exile 2", 2024, "game", "name_mismatch"),
    ("Grand Theft Auto IV: Complete Edition", 2008, "Grand Theft Auto IV: The Complete Edition", 2010, "game", "ok"),
    ("Valheim", 2025, "Valheim", 2021, "game", "ok"),
    ("Heroes & Generals", 2016, "Heroes &amp; Generals Playtest", 2016, "game", "name_mismatch"),
    ("7 Days to Die", 2024, "7 Days to Die", 2013, "game", "ok"),
    ("Deceit", 2017, "Deceit 2", 2022, "game", "name_mismatch"),
    ("Forza Horizon 4", 2018, "Forza Horizon 4: Fortune Island", 2019, "game", "name_mismatch"),
    ("Realm Royale", 2018, "Realm Royale Reforged", 2018, "game", "name_mismatch"),
    ("Total War: THREE KINGDOMS", 2019, "Total War: THREE KINGDOMS - Shi Xie", 2019, "dlc", "not_game"),
    ("Prison Architect", 2015, "Prison Architect Playtest", 2023, "game", "name_mismatch"),
    ("The Cycle: Frontier", 2022, "The Cycle Playtest", 2022, "game", "name_mismatch"),
    ("HITMAN 2", 2018, "Hitman 2: Silent Assassin", 2002, "game", "name_mismatch"),
    ("POSTAL 2", 2013, "POSTAL 2", 2003, "game", "ok"),
    ("Ready or Not", 2023, "Ready or Not [archive]", 2023, "game", "name_mismatch"),
    ("Stray", 2022, "Fantasy Maiden Wars - DREAM OF THE STRAY DREAMER -", 2025, "game", "name_mismatch"),
    ("Metro 2033 Redux", 2014, "Metro 2033", 2010, "game", "name_mismatch"),
    ("Crossout", 2017, "Crossout Remastered", 2017, "game", "ok"),
    ("Gloria Victis", 2020, "Gloria Victis: Medieval MMORPG", 2020, "game", "name_mismatch"),
    ("FragPunk", 2025, "FragPunk Pioneer Bundle", 2025, "game", "name_mismatch"),
    ("Delta Force", 2025, "Delta Force 1", 1998, "game", "name_mismatch"),
    ("Call of Duty: Modern Warfare 3 (2011)", 2011, "Call of Duty®: Modern Warfare® III", 2023, "game", "year_mismatch"),
    ("Need for Speed Heat", 2019, "Need for Speed™ Heat - McLaren F1 Black Market Delivery", 2020, "game", "name_mismatch"),
]


def test_report_fixture_covers_all_findings() -> None:
    assert len(CASES) == 43  # 42 mismatch + 1 reclassified


@pytest.mark.parametrize(("title", "year", "steam_name", "steam_year", "steam_type", "reason"), CASES)
def test_report_case(title, year, steam_name, steam_year, steam_type, reason) -> None:
    verdict = steam_identity_verdict(
        title, year, steam_name=steam_name, steam_year=steam_year, steam_type=steam_type
    )
    assert verdict.reason == reason
    assert verdict.ok is (reason == "ok")


@pytest.mark.parametrize(
    ("title", "year", "steam_name", "steam_year", "reason"),
    [
        ("Elden Ring", 2022, "Elden Ring", 2022, "ok"),
        ("Tom Clancy’s Rainbow Six Siege", 2015, "Tom Clancy's Rainbow Six® Siege", 2015, "ok"),
        ("Doom (2016)", 2016, "DOOM", 2016, "ok"),
        ("Resident Evil 4 Remake", 2023, "Resident Evil 4 (2005)", 2007, "year_mismatch"),
        ("Resident Evil 4 Remake", 2023, "Resident Evil 4", 2007, "year_mismatch"),
        ("Borderlands 3", 2019, "Borderlands 2", 2012, "name_mismatch"),
        ("Hades", 2020, "Hades II", 2024, "name_mismatch"),
        ("Age of Empires II: Definitive Edition", 2019, "Age of Empires II (Retired)", 2013, "qualifier_mismatch"),
    ],
)
def test_extra_rules(title, year, steam_name, steam_year, reason) -> None:
    verdict = steam_identity_verdict(title, year, steam_name=steam_name, steam_year=steam_year)
    assert verdict.reason == reason
