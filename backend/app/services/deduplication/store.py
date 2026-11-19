"""Database-backed duplicate detection, preview and consolidation."""

from collections import defaultdict
from typing import Protocol

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, load_only

from ...models import (
    AiCatalogChange,
    CatalogQualityReview,
    ExternalId,
    Game,
    GameSearchAlias,
    PriceSnapshot,
    RatingSnapshot,
    SlugRedirect,
    UserCollection,
)
from ..keyset_scan import SCAN_BATCH_SIZE, keyset_batches
from .matching import duplicate_key, duplicate_quality_key, games_are_duplicates
from .merge import merge_game_data


class IndexedIdentity(Protocol):
    id: int
    title: str
    slug: str
    release_year: int
    content_type: str


class _ScannedIdentity(Protocol):
    id: int
    title: str
    slug: str
    release_year: int


DuplicateCandidateIndex = dict[tuple[str, str], dict[int, IndexedIdentity]]


def add_duplicate_candidate(
    index: DuplicateCandidateIndex,
    game: IndexedIdentity,
) -> None:
    """Add one lightweight identity to every key used by duplicate matching."""
    game_id = int(game.id or 0)
    if game_id <= 0:
        return
    for key in set(duplicate_key(game)):
        if key:
            index.setdefault((game.content_type, key), {})[game_id] = game


def build_duplicate_candidate_index(db: Session) -> DuplicateCandidateIndex:
    """Load one compact index for batch imports instead of scanning per row."""
    index: DuplicateCandidateIndex = {}
    rows = db.execute(
        select(Game.id, Game.title, Game.slug, Game.release_year, Game.content_type)
        .execution_options(yield_per=1000)
    )
    for row in rows:
        add_duplicate_candidate(index, row)
    return index


def _indexed_candidates(
    index: DuplicateCandidateIndex,
    game: Game,
) -> list[IndexedIdentity]:
    candidates: dict[int, IndexedIdentity] = {}
    for key in set(duplicate_key(game)):
        candidates.update(index.get((game.content_type, key), {}))
    return list(candidates.values())


def find_existing_duplicate(
    db: Session,
    game: Game,
    *,
    candidate_index: DuplicateCandidateIndex | None = None,
) -> Game | None:
    # Scan on the three title columns only — loading full Game rows (with their
    # large source_scores/screenshots JSON) for every candidate on every import
    # made this O(catalog) in bytes. Full objects are fetched just for matches.
    candidate_rows = (
        _indexed_candidates(candidate_index, game)
        if candidate_index is not None
        else db.execute(
            select(Game.id, Game.title, Game.slug, Game.release_year).where(
                Game.content_type == game.content_type,
                Game.id != (game.id or 0),
            )
        ).all()
    )
    match_ids = [
        row.id
        for row in candidate_rows
        if row.id != (game.id or 0) and games_are_duplicates(row, game)
    ]
    if not match_ids:
        return None
    matches = db.scalars(select(Game).where(Game.id.in_(match_ids))).all()
    return max(matches, key=duplicate_quality_key)


def _build_external_id_groups(db: Session) -> dict[int, set[int]]:
    """Return {game_id: set of game_ids sharing any (source, external_id)}."""
    rows = db.execute(select(ExternalId.game_id, ExternalId.source, ExternalId.external_id)).all()
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


# Duplicate detection reads only these. The old `select(Game)` pulled every column of
# the whole catalog (~50k rows with their JSON blobs) in one statement and hit the
# statement timeout in production.
_IDENTITY_COLUMNS = (Game.id, Game.title, Game.slug, Game.release_year)
# What choosing a keeper (`duplicate_quality_key`) and describing a group read.
_KEEPER_COLUMNS = (
    Game.id, Game.title, Game.slug, Game.release_year, Game.developer, Game.publisher,
    Game.summary, Game.cover_url, Game.screenshots, Game.platforms, Game.source_scores,
    Game.rank_score, Game.metrix_score,
)
_GROUP_LOAD_CHUNK = 500


def find_duplicate_id_groups(db: Session, *, batch_size: int = SCAN_BATCH_SIZE) -> list[list[int]]:
    """Detect duplicate clusters as game ids (2+ per group), scanning identity columns
    in keyset batches. Read-only; leaves the session's transaction to the caller."""
    games = [
        row
        for batch in keyset_batches(db, select(*_IDENTITY_COLUMNS), Game.id, batch_size=batch_size, release=False)
        for row in batch
    ]
    games_by_id = {game.id: game for game in games}
    ids_by_key: dict[str, set[int]] = defaultdict(set)
    for game in games:
        for key in set(duplicate_key(game)):
            if key:
                ids_by_key[key].add(game.id)

    ext_id_groups = _build_external_id_groups(db)

    found: list[list[int]] = []
    visited: set[int] = set()
    for game in games:
        if game.id in visited:
            continue
        group = _collect_group(game, games_by_id, ids_by_key, ext_id_groups, visited)
        if len(group) >= 2:
            found.append([item.id for item in group])
    return found


def _load_groups(db: Session, id_groups: list[list[int]], *, full: bool) -> list[list[Game]]:
    """Game objects for the grouped ids only; `full=False` loads just the keeper columns."""
    ids = [game_id for group in id_groups for game_id in group]
    by_id: dict[int, Game] = {}
    for start in range(0, len(ids), _GROUP_LOAD_CHUNK):
        stmt = select(Game).where(Game.id.in_(ids[start:start + _GROUP_LOAD_CHUNK]))
        if not full:
            stmt = stmt.options(load_only(*_KEEPER_COLUMNS))
        by_id.update((game.id, game) for game in db.scalars(stmt))
    groups = [[by_id[game_id] for game_id in group if game_id in by_id] for group in id_groups]
    return [group for group in groups if len(group) >= 2]


def find_duplicate_groups(db: Session, *, full: bool = True) -> list[list[Game]]:
    """Detect duplicate clusters without modifying anything. Each group has 2+ games.

    `full=False` loads only the columns keeper selection reads (previews, dry runs).
    """
    return _load_groups(db, find_duplicate_id_groups(db), full=full)


def _collect_group(
    game: _ScannedIdentity,
    games_by_id: dict[int, _ScannedIdentity],
    ids_by_key: dict[str, set[int]],
    ext_id_groups: dict[int, set[int]],
    visited: set[int],
) -> list[_ScannedIdentity]:
    candidate_ids: set[int] = set()
    for key in set(duplicate_key(game)):
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
    return group


def preview_duplicate_groups(db: Session) -> list[dict[str, object]]:
    """Read-only report of what consolidate_duplicate_games would merge."""
    preview: list[dict[str, object]] = []
    for group in find_duplicate_groups(db, full=False):
        keeper = max(group, key=duplicate_quality_key)
        preview.append({
            "keeper": _describe(keeper),
            "duplicates": [_describe(item) for item in group if item.id != keeper.id],
        })
    return preview


def _describe(game: Game) -> dict[str, object]:
    return {
        "id": game.id,
        "title": game.title,
        "slug": game.slug,
        "release_year": game.release_year,
    }


def duplicate_group_game_ids(db: Session) -> list[int]:
    """Every game id that sits in a duplicate group (used to verify Steam ids first)."""
    return [game_id for group in find_duplicate_id_groups(db) for game_id in group]


def consolidate_duplicate_games(db: Session, *, dry_run: bool = False) -> dict[str, object]:
    """Merge duplicate groups into their best row, leaving 301 redirects behind.

    `dry_run=True` changes nothing and returns the groups it would merge. Steam ids
    only travel from a duplicate to the keeper when they are verified; callers that
    want ids verified before merging run `audit_steam_ids` on `duplicate_group_game_ids`.
    """
    id_groups = find_duplicate_id_groups(db)
    if dry_run:
        previews = [_preview_group(group) for group in _load_groups(db, id_groups, full=False)]
        return {
            "dry_run": True,
            "merged_groups": len(previews),
            "removed": sum(len(item["duplicates"]) for item in previews),  # type: ignore[arg-type]
            "groups": previews,
        }

    removed = 0
    merged_groups = 0
    for id_group in id_groups:
        # Full rows (merge copies every field), one group at a time to bound memory.
        loaded = _load_groups(db, [id_group], full=True)
        if not loaded:
            continue
        group = loaded[0]
        keeper = max(group, key=duplicate_quality_key)
        for duplicate in (item for item in group if item.id != keeper.id):
            merge_game_data(keeper, duplicate)
            _inherit_verified_steam_id(db, keeper, duplicate)
            _reassign_related_rows(db, keeper.id, duplicate.id)
            _record_slug_redirect(db, keeper, duplicate)
            # The session runs with autoflush=False, so the ExternalId re-parenting
            # above is still pending here. Flush it before the Core DELETE — its
            # ON DELETE CASCADE would otherwise remove those rows first and the
            # deferred UPDATE statements would raise StaleDataError at commit.
            db.flush()
            db.execute(delete(Game).where(Game.id == duplicate.id))
            removed += 1
        db.add(keeper)
        merged_groups += 1

    db.commit()
    return {"dry_run": False, "merged_groups": merged_groups, "removed": removed}


def _preview_group(group: list[Game]) -> dict[str, object]:
    keeper = max(group, key=duplicate_quality_key)
    return {
        "keeper": _describe(keeper),
        "duplicates": [_describe(item) for item in group if item.id != keeper.id],
    }


def _inherit_verified_steam_id(db: Session, keeper: Game, duplicate: Game) -> None:
    """Carry the duplicate's Steam id over only when appdetails verified it."""
    if keeper.steam_app_id is None and duplicate.steam_app_id is not None and duplicate.steam_app_id_verified_at:
        keeper.steam_app_id = duplicate.steam_app_id
        keeper.steam_app_id_verified_at = duplicate.steam_app_id_verified_at


def _record_slug_redirect(db: Session, keeper: Game, duplicate: Game) -> None:
    """Old slug -> keeper (301), and re-point redirects that already led to the duplicate."""
    db.execute(update(SlugRedirect).where(SlugRedirect.game_id == duplicate.id).values(game_id=keeper.id))
    if duplicate.slug and duplicate.slug != keeper.slug:
        db.execute(
            pg_insert(SlugRedirect)
            .values(old_slug=duplicate.slug, game_id=keeper.id)
            .on_conflict_do_update(index_elements=[SlugRedirect.old_slug], set_={"game_id": keeper.id})
        )


def _reassign_related_rows(db: Session, keeper_id: int, duplicate_id: int) -> None:
    # ExternalId: skip rows where (game_id=keeper, source, external_id) already exists
    keeper = db.get(Game, keeper_id)
    existing_ext = db.scalars(select(ExternalId).where(ExternalId.game_id == keeper_id)).all()
    existing_keys = {(e.source, e.external_id) for e in existing_ext}
    for ext in db.scalars(select(ExternalId).where(ExternalId.game_id == duplicate_id)).all():
        if (ext.source, ext.external_id) in existing_keys:
            db.delete(ext)
        elif ext.source == "Steam" and not _steam_external_id_may_move(keeper, ext):
            # An unverified (or conflicting) Steam id must not be re-parented onto the keeper.
            db.delete(ext)
        else:
            ext.game_id = keeper_id
    for model in (RatingSnapshot, PriceSnapshot, CatalogQualityReview, AiCatalogChange, GameSearchAlias):
        db.execute(update(model).where(model.game_id == duplicate_id).values(game_id=keeper_id))
    _reassign_user_collections(db, keeper_id, duplicate_id)


def _reassign_user_collections(db: Session, keeper_id: int, duplicate_id: int) -> None:
    """Users' lists must survive a merge: games.id deletes CASCADE into user_collections.

    A user who saved both copies keeps one row (the unique key is user, game, list type);
    every other row moves to the keeper before the duplicate is deleted.
    """
    kept = set(
        db.execute(
            select(UserCollection.user_id, UserCollection.collection_type).where(UserCollection.game_id == keeper_id)
        ).all()
    )
    for row in db.scalars(select(UserCollection).where(UserCollection.game_id == duplicate_id)).all():
        if (row.user_id, row.collection_type) in kept:
            db.delete(row)
        else:
            row.game_id = keeper_id
            kept.add((row.user_id, row.collection_type))
    db.flush()


def _steam_external_id_may_move(keeper: Game | None, ext: ExternalId) -> bool:
    return (
        keeper is not None
        and keeper.steam_app_id is not None
        and keeper.steam_app_id_verified_at is not None
        and str(keeper.steam_app_id) == ext.external_id
    )
