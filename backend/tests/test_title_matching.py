from datetime import date

from app.integrations.opencritic import _best_search_result, _extract_score
from app.integrations.rawg_score import _best_rawg_result, _parse_rawg_date
from app.integrations.title_matching import title_match_quality, titles_match
from app.services.metadata_backfill import safe_url


def test_title_matching_normalizes_punctuation_and_roman_numerals() -> None:
    assert titles_match("The Witcher III: Wild Hunt", "The Witcher 3 - Wild Hunt")


def test_title_matching_rejects_different_sequels_and_distant_releases() -> None:
    assert not titles_match("Portal", "Portal 2")
    assert not titles_match(
        "Resident Evil 4",
        "Resident Evil 4",
        expected_year=2005,
        candidate_year=2023,
    )


def test_title_matching_accepts_cosmetic_edition_suffixes() -> None:
    assert title_match_quality("Hades", "Hades Complete Edition") == 0.99


def test_rawg_result_picker_uses_title_and_year_instead_of_first_result() -> None:
    results = [
        {"id": 1, "name": "Portal 2", "released": "2011-04-18"},
        {"id": 2, "name": "Portal", "released": "2007-10-10"},
    ]
    assert _best_rawg_result("Portal", results, 2007) == results[1]
    assert _parse_rawg_date("2007-10-10") == date(2007, 10, 10)
    assert _parse_rawg_date("not-a-date") is None


def test_opencritic_result_picker_and_score_do_not_substitute_recommendation_rate() -> None:
    results = [
        {"id": 12, "name": "DOOM Eternal", "firstReleaseDate": "2020-03-20"},
        {"id": 11, "name": "DOOM", "firstReleaseDate": "2016-05-13"},
    ]
    assert _best_search_result("DOOM", results, 2016) == results[1]
    assert _extract_score({"topCriticScore": None, "percentRecommended": 91}) == (None, 91.0)
    assert _extract_score({"topCriticScore": 101, "percentRecommended": 50}) == (None, 50.0)


def test_metadata_urls_reject_credentials_whitespace_and_non_http_schemes() -> None:
    assert safe_url("images.example/game.jpg") == "https://images.example/game.jpg"
    assert safe_url("https://images.example/game.jpg") == "https://images.example/game.jpg"
    assert safe_url("https://user:secret@images.example/game.jpg") is None
    assert safe_url("https://images.example/bad image.jpg") is None
    assert safe_url("javascript:alert(1)") is None
