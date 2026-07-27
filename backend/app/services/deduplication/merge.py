"""Folding a duplicate game's data into the keeper, then rescoring the keeper."""

from ...game_signals import safe_review_count, valid_score
from ...models import Game
from ..metadata import invalidate_summary_audit
from .matching import UNKNOWN_YEAR, duplicate_quality_key

_COPY_IF_EMPTY_ATTRS = (
    "developer",
    "publisher",
    "metacritic_score",
    "image_url",
    "website_url",
    "ratings_refreshed_at",
    "metadata_refreshed_at",
)


def merge_game_data(keeper: Game, duplicate: Game) -> bool:
    from ...integrations.sync import calculate_metrix_score, compute_rank_fields

    changed = _merge_summaries(keeper, duplicate)
    changed = _merge_release(keeper, duplicate) or changed
    changed = _merge_empty_fields(keeper, duplicate) or changed
    changed = _merge_playtime(keeper, duplicate) or changed
    _merge_awards(keeper, duplicate)
    _merge_collections(keeper, duplicate)

    keeper.source_scores = _merge_source_scores(keeper.source_scores, duplicate.source_scores)
    keeper.metrix_score = calculate_metrix_score(keeper.source_scores)
    rank_score, is_rankable, _ = compute_rank_fields(keeper)
    keeper.rank_score = rank_score
    keeper.is_rankable = is_rankable
    return changed


def _merge_summaries(keeper: Game, duplicate: Game) -> bool:
    changed = False
    if duplicate.summary and len(duplicate.summary) > len(keeper.summary or ""):
        keeper.summary = duplicate.summary
        invalidate_summary_audit(keeper)
        changed = True
    if duplicate.summary_short and not keeper.summary_short:
        keeper.summary_short = duplicate.summary_short
        changed = True
    return changed


def _merge_release(keeper: Game, duplicate: Game) -> bool:
    if duplicate.release_year != UNKNOWN_YEAR and (
        keeper.release_year == UNKNOWN_YEAR
        or duplicate_quality_key(duplicate) > duplicate_quality_key(keeper)
    ):
        keeper.release_date = duplicate.release_date
        keeper.release_year = duplicate.release_year
        return True
    return False


def _merge_empty_fields(keeper: Game, duplicate: Game) -> bool:
    changed = False
    for attr in _COPY_IF_EMPTY_ATTRS:
        if getattr(keeper, attr) in (None, "") and getattr(duplicate, attr) not in (None, ""):
            setattr(keeper, attr, getattr(duplicate, attr))
            changed = True
    if not keeper.cover_url and duplicate.cover_url:
        keeper.cover_url = duplicate.cover_url
        changed = True
    if not keeper.early_access_date and duplicate.early_access_date:
        keeper.early_access_date = duplicate.early_access_date
        changed = True
    if not keeper.official_release_date and duplicate.official_release_date:
        keeper.official_release_date = duplicate.official_release_date
        changed = True
    return changed


def _merge_playtime(keeper: Game, duplicate: Game) -> bool:
    if (duplicate.playtime_minutes or 0) > (keeper.playtime_minutes or 0):
        keeper.playtime_minutes = duplicate.playtime_minutes
        return True
    return False


def _merge_awards(keeper: Game, duplicate: Game) -> None:
    keeper.award_count = max(keeper.award_count or 0, duplicate.award_count or 0)
    keeper.award_nominations = max(keeper.award_nominations or 0, duplicate.award_nominations or 0)
    if keeper.goty_year is None:
        keeper.goty_year = duplicate.goty_year


def _merge_collections(keeper: Game, duplicate: Game) -> None:
    keeper.genres = _merge_unique_strings(keeper.genres, duplicate.genres)
    keeper.platforms = _merge_unique_strings(keeper.platforms, duplicate.platforms)
    keeper.game_modes = _merge_unique_strings(keeper.game_modes, duplicate.game_modes)
    keeper.screenshots = _merge_unique_strings(keeper.screenshots, duplicate.screenshots)
    keeper.system_requirements = _merge_json_objects(keeper.system_requirements, duplicate.system_requirements)
    keeper.dlcs = _merge_json_objects(keeper.dlcs, duplicate.dlcs)
    keeper.similar_games = _merge_json_objects(keeper.similar_games, duplicate.similar_games)


def _merge_unique_strings(left: list[str] | None, right: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in [*(left or []), *(right or [])]:
        if not isinstance(item, str):
            continue
        key = item.lower()
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _score_entry_key(score: dict) -> tuple[int, int, float]:
    return (
        1 if valid_score(score) else 0,
        safe_review_count(score),
        float(score.get("score") or 0) if valid_score(score) else 0.0,
    )


def _merge_source_scores(left: list[dict] | None, right: list[dict] | None) -> list[dict]:
    by_source: dict[str, dict] = {}
    for score in [*(left or []), *(right or [])]:
        if not isinstance(score, dict):
            continue
        source = str(score.get("source") or "")
        if not source:
            continue
        existing = by_source.get(source)
        if existing is None or _score_entry_key(score) > _score_entry_key(existing):
            by_source[source] = dict(score)
    return list(by_source.values())


def _merge_json_objects(left: list[dict] | None, right: list[dict] | None) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for item in [*(left or []), *(right or [])]:
        key = str(item)
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result
