import re
from collections import defaultdict

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..models import ExternalId, Game, PriceSnapshot, RatingSnapshot


_SAME_TITLE_YEAR_TOLERANCE = 4
_EDITION_YEAR_TOLERANCE = 10
_UNKNOWN_YEAR = 1970

_EDITION_SUFFIX_RE = re.compile(
    r"[\s:–—\-]+(?:"
    r"definitive(?: edition)?|royal(?: edition)?|remastered(?: edition)?|enhanced(?: edition)?|"
    r"complete(?: edition)?|goty(?: edition)?|game of the year(?: edition)?|"
    r"gold(?: edition)?|platinum(?: edition)?|legendary(?: edition)?|"
    r"ultimate(?: edition)?|deluxe(?: edition)?|director'?s cut|expanded(?: edition)?|"
    r"special(?: edition)?|collector'?s(?: edition)?|the final cut|final cut|"
    r"redux|hd(?: remaster)?|4k|the complete edition|landmark edition|komplete(?: edition)?|"
    r"anniversary edition"
    r")$",
    re.IGNORECASE,
)

# Stricter suffix regex used only for _base_title (no "anniversary", no "gold" standalone)
_BASE_SUFFIX_RE = re.compile(
    r"[\s:–—\-]+(?:"
    r"definitive(?: edition)?|royal(?: edition)?|remastered(?: edition)?|enhanced(?: edition)?|"
    r"goty(?: edition)?|game of the year(?: edition)?|"
    r"gold edition|platinum(?: edition)?|"
    r"director'?s cut|"
    r"special(?: edition)?|collector'?s(?: edition)?|the final cut|final cut|"
    r"redux|hd(?: remaster)?|4k|landmark edition|komplete(?: edition)?|"
    r"anniversary edition"
    r")$",
    re.IGNORECASE,
)

# Strip parenthesized year disambiguators: "DOOM (2016)" → "DOOM", "Prey (2017)" → "Prey"
_YEAR_DISAMBIG_RE = re.compile(r"\s*\(\d{4}(?:[^)]*?)?\)\s*$")

# Strip parenthesized qualifiers added by importers: "(Classic)", "(2010 Edition)", etc.
_PAREN_QUALIFIER_RE = re.compile(
    r"\s*\((?:classic|retired|open beta|beta|playtest|\d{4}\s+edition)\)\s*$",
    re.IGNORECASE,
)

# Subtitle strip: ": <subtitle>" after the main title (for "Fall Guys: Ultimate Knockout")
_SUBTITLE_RE = re.compile(r"\s*[:\-–—]\s+.+$")

_ROMAN_TO_ARABIC = {
    "ii": "2", "iii": "3", "iv": "4", "vi": "6", "vii": "7", "viii": "8",
    "ix": "9", "xi": "11", "xii": "12",
}
_ROMAN_RE = re.compile(r"\b(viii|vii|vi|iv|iii|ii|ix|xii|xi)\b", re.IGNORECASE)


def _normalize_roman(value: str) -> str:
    return _ROMAN_RE.sub(lambda m: _ROMAN_TO_ARABIC.get(m.group().lower(), m.group()), value)


def normalized_title(value: str) -> str:
    value = value.replace("+", " plus ")
    value = _normalize_roman(value)
    return "".join(ch.casefold() for ch in value if ch.isalnum())


def canonical_title(value: str) -> str:
    stripped = _EDITION_SUFFIX_RE.sub("", value).strip()
    return normalized_title(stripped)


def _base_title(value: str) -> str:
    """Remove year disambiguators, importer qualifiers and edition suffixes, then normalize."""
    t = _YEAR_DISAMBIG_RE.sub("", value).strip()
    t = _PAREN_QUALIFIER_RE.sub("", t).strip()
    t = _BASE_SUFFIX_RE.sub("", t).strip()
    return normalized_title(t)


def _subtitle_stripped(value: str) -> str:
    """Strip colon/dash subtitle: 'Fall Guys: Ultimate Knockout' → 'fallguys'."""
    t = _SUBTITLE_RE.sub("", value).strip()
    return normalized_title(t)


def _years_match(left: int, right: int, tolerance: int) -> bool:
    if left == _UNKNOWN_YEAR or right == _UNKNOWN_YEAR:
        return True
    return abs(left - right) <= tolerance


def _duplicate_key(game: Game) -> tuple[str, str, str]:
    return normalized_title(game.title), canonical_title(game.title), _base_title(game.title)


def _slug_stem(slug: str) -> str:
    return re.sub(r"-\d{3,}$", "", slug.lower())


def games_are_duplicates(left: Game, right: Game) -> bool:
    left_norm, left_canon, left_base = _duplicate_key(left)
    right_norm, right_canon, right_base = _duplicate_key(right)

    # 1. Exact normalized match (roman numerals already converted)
    if left_norm and left_norm == right_norm:
        if left.title.strip().casefold() == right.title.strip().casefold():
            return True
        if _slug_stem(left.slug) == _slug_stem(right.slug):
            return True
        return _years_match(left.release_year, right.release_year, _SAME_TITLE_YEAR_TOLERANCE)

    # 2. Edition variant of same game (GOTY / Remastered / Definitive Edition …)
    # Guard: if either title contains "Remake" (a distinct product), skip this path
    if left_canon and left_canon == right_canon:
        left_has_remake = re.search(r"\bremake\b", left.title, re.IGNORECASE)
        right_has_remake = re.search(r"\bremake\b", right.title, re.IGNORECASE)
        if bool(left_has_remake) != bool(right_has_remake):
            pass  # one is "Remake", other is original → not duplicates via edition path
        elif left_canon != left_norm or right_canon != right_norm:
            return _years_match(left.release_year, right.release_year, _EDITION_YEAR_TOLERANCE)

    # 3. Year-disambiguated / paren-qualifier / edition-stripped titles:
    #    "DOOM (2016)" ↔ "DOOM", "Prey (2017)" ↔ "Prey",
    #    "Shadow Warrior (Classic)" ↔ "Shadow Warrior",
    #    "Mass Effect 2 (2010 Edition)" ↔ "Mass Effect 2",
    #    "Mafia II (Classic)" ↔ "Mafia II: Definitive Edition"
    if left_base and left_base == right_base:
        # At least one side must have had something stripped (otherwise norm-match above handled it)
        if left_base != left_norm or left_base != right_norm:
            return _years_match(left.release_year, right.release_year, _EDITION_YEAR_TOLERANCE)

    return False


def total_review_count(game: Game) -> int:
    return sum(int(s.get("review_count", 0)) for s in game.source_scores or [])


def duplicate_quality_key(game: Game) -> tuple[int, int, int, int, int, float, int]:
    slug_looks_curated = not re.search(r"-\d+$", game.slug)
    metadata_score = sum([
        1 if game.release_year != _UNKNOWN_YEAR else 0,
        1 if game.developer else 0,
        1 if game.publisher else 0,
        1 if game.summary and len(game.summary) > 120 else 0,
        1 if game.cover_url else 0,
        1 if game.screenshots else 0,
    ])
    return (
        1 if slug_looks_curated else 0,
        1 if game.release_year != _UNKNOWN_YEAR else 0,
        metadata_score,
        game.live_primary_source_count,
        total_review_count(game),
        game.rank_score or game.metrix_score,
        -(game.id or 0),
    )


def dedupe_games_in_memory(games: list[Game]) -> list[Game]:
    deduped: list[Game] = []
    idx_by_key: dict[str, list[int]] = defaultdict(list)

    def register(game: Game, idx: int) -> None:
        for key in set(_duplicate_key(game)):
            if key and idx not in idx_by_key[key]:
                idx_by_key[key].append(idx)

    def find_match(game: Game) -> int | None:
        for key in set(_duplicate_key(game)):
            for idx in idx_by_key.get(key, []):
                if games_are_duplicates(deduped[idx], game):
                    return idx
        return None

    for game in games:
        existing_idx = find_match(game)
        if existing_idx is None:
            new_idx = len(deduped)
            deduped.append(game)
            register(game, new_idx)
        elif duplicate_quality_key(game) > duplicate_quality_key(deduped[existing_idx]):
            deduped[existing_idx] = game
            register(game, existing_idx)

    return deduped


def find_existing_duplicate(db: Session, game: Game) -> Game | None:
    candidates = list(
        db.scalars(
            select(Game).where(
                Game.content_type == game.content_type,
                Game.id != (game.id or 0),
            )
        )
    )
    matches = [candidate for candidate in candidates if games_are_duplicates(candidate, game)]
    if not matches:
        return None
    return max(matches, key=duplicate_quality_key)


def _merge_unique_strings(left: list[str] | None, right: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in [*(left or []), *(right or [])]:
        key = item.lower()
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _score_entry_key(score: dict) -> tuple[int, int, float]:
    return (
        1 if score.get("status") == "live" else 0,
        int(score.get("review_count") or 0),
        float(score.get("score") or 0),
    )


def _merge_source_scores(left: list[dict] | None, right: list[dict] | None) -> list[dict]:
    by_source: dict[str, dict] = {}
    for score in [*(left or []), *(right or [])]:
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


def merge_game_data(keeper: Game, duplicate: Game) -> bool:
    from ..integrations.sync import calculate_metrix_score, compute_rank_fields

    changed = False
    if duplicate.summary and len(duplicate.summary) > len(keeper.summary or ""):
        keeper.summary = duplicate.summary
        changed = True
    if duplicate.summary_short and not keeper.summary_short:
        keeper.summary_short = duplicate.summary_short
        changed = True
    if duplicate.release_year != _UNKNOWN_YEAR and (
        keeper.release_year == _UNKNOWN_YEAR or duplicate_quality_key(duplicate) > duplicate_quality_key(keeper)
    ):
        keeper.release_date = duplicate.release_date
        keeper.release_year = duplicate.release_year
        changed = True
    for attr in ("developer", "publisher", "metacritic_score", "image_url", "website_url", "ratings_refreshed_at", "metadata_refreshed_at"):
        if getattr(keeper, attr) in (None, "") and getattr(duplicate, attr) not in (None, ""):
            setattr(keeper, attr, getattr(duplicate, attr))
            changed = True
    if (not keeper.cover_url) and duplicate.cover_url:
        keeper.cover_url = duplicate.cover_url
        changed = True
    if not keeper.early_access_date and duplicate.early_access_date:
        keeper.early_access_date = duplicate.early_access_date
        changed = True
    if not keeper.official_release_date and duplicate.official_release_date:
        keeper.official_release_date = duplicate.official_release_date
        changed = True
    if (duplicate.playtime_minutes or 0) > (keeper.playtime_minutes or 0):
        keeper.playtime_minutes = duplicate.playtime_minutes
        changed = True
    keeper.award_count = max(keeper.award_count or 0, duplicate.award_count or 0)
    keeper.award_nominations = max(keeper.award_nominations or 0, duplicate.award_nominations or 0)
    if keeper.goty_year is None:
        keeper.goty_year = duplicate.goty_year
    keeper.genres = _merge_unique_strings(keeper.genres, duplicate.genres)
    keeper.platforms = _merge_unique_strings(keeper.platforms, duplicate.platforms)
    keeper.screenshots = _merge_unique_strings(keeper.screenshots, duplicate.screenshots)
    keeper.system_requirements = _merge_json_objects(keeper.system_requirements, duplicate.system_requirements)
    keeper.dlcs = _merge_json_objects(keeper.dlcs, duplicate.dlcs)
    keeper.similar_games = _merge_json_objects(keeper.similar_games, duplicate.similar_games)
    keeper.source_scores = _merge_source_scores(keeper.source_scores, duplicate.source_scores)
    keeper.metrix_score = calculate_metrix_score(keeper.source_scores)
    rank_score, is_rankable, _ = compute_rank_fields(keeper)
    keeper.rank_score = rank_score
    keeper.is_rankable = is_rankable
    return changed


def _reassign_related_rows(db: Session, keeper_id: int, duplicate_id: int) -> None:
    # ExternalId: skip rows where (game_id=keeper, source, external_id) already exists
    existing_ext = db.scalars(
        select(ExternalId).where(ExternalId.game_id == keeper_id)
    ).all()
    existing_keys = {(e.source, e.external_id) for e in existing_ext}
    for ext in db.scalars(select(ExternalId).where(ExternalId.game_id == duplicate_id)).all():
        if (ext.source, ext.external_id) in existing_keys:
            db.delete(ext)
        else:
            ext.game_id = keeper_id
    for model in (RatingSnapshot, PriceSnapshot):
        db.execute(
            update(model)
            .where(model.game_id == duplicate_id)
            .values(game_id=keeper_id)
        )


def _build_external_id_groups(db: Session) -> dict[int, set[int]]:
    """Return {game_id: set of game_ids sharing any (source, external_id)}."""
    rows = db.execute(
        select(ExternalId.game_id, ExternalId.source, ExternalId.external_id)
    ).all()
    by_ext: dict[tuple[str, str], list[int]] = defaultdict(list)
    for game_id, source, ext_id in rows:
        if ext_id:
            by_ext[(source, ext_id)].append(game_id)

    groups: dict[int, set[int]] = defaultdict(set)
    for game_ids in by_ext.values():
        if len(game_ids) > 1:
            for gid in game_ids:
                groups[gid].update(game_ids)
    return groups


def consolidate_duplicate_games(db: Session) -> dict[str, int]:
    games = list(db.scalars(select(Game).order_by(Game.id)).all())
    games_by_id = {game.id: game for game in games}
    ids_by_key: dict[str, set[int]] = defaultdict(set)
    for game in games:
        for key in set(_duplicate_key(game)):
            if key:
                ids_by_key[key].add(game.id)

    ext_id_groups = _build_external_id_groups(db)

    removed = 0
    merged_groups = 0
    visited: set[int] = set()

    for game in games:
        if game.id in visited:
            continue
        candidate_ids: set[int] = set()
        for key in set(_duplicate_key(game)):
            candidate_ids.update(ids_by_key.get(key, set()))
        # Also consider games that share an external ID — but only if titles also match.
        # (External ID conflicts can be data errors where two distinct games got the same ID.)
        candidate_ids.update(ext_id_groups.get(game.id, set()))
        group = [game]
        visited.add(game.id)
        for candidate_id in candidate_ids:
            if candidate_id in visited or candidate_id not in games_by_id:
                continue
            candidate = games_by_id[candidate_id]
            if games_are_duplicates(game, candidate):
                group.append(candidate)
                visited.add(candidate.id)
        if len(group) < 2:
            continue

        keeper = max(group, key=duplicate_quality_key)
        duplicates = [item for item in group if item.id != keeper.id]
        for duplicate in duplicates:
            merge_game_data(keeper, duplicate)
            _reassign_related_rows(db, keeper.id, duplicate.id)
            db.execute(delete(Game).where(Game.id == duplicate.id))
            removed += 1
        db.add(keeper)
        merged_groups += 1

    db.commit()
    return {"merged_groups": merged_groups, "removed": removed}
