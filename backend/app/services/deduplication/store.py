"""Database-backed duplicate detection, preview and consolidation."""

from collections import defaultdict

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ...models import ExternalId, Game, PriceSnapshot, RatingSnapshot
from .matching import duplicate_key, duplicate_quality_key, games_are_duplicates
from .merge import merge_game_data


def find_existing_duplicate(db: Session, game: Game) -> Game | None:
    candidates = db.scalars(
        select(Game).where(
            Game.content_type == game.content_type,
            Game.id != (game.id or 0),
        )
    )
    matches = [candidate for candidate in candidates if games_are_duplicates(candidate, game)]
    if not matches:
        return None
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


def find_duplicate_groups(db: Session) -> list[list[Game]]:
    """Detect duplicate clusters without modifying anything. Each group has 2+ games."""
    games = list(db.scalars(select(Game).order_by(Game.id)).all())
    games_by_id = {game.id: game for game in games}
    ids_by_key: dict[str, set[int]] = defaultdict(set)
    for game in games:
        for key in set(duplicate_key(game)):
            if key:
                ids_by_key[key].add(game.id)

    ext_id_groups = _build_external_id_groups(db)

    found: list[list[Game]] = []
    visited: set[int] = set()
    for game in games:
        if game.id in visited:
            continue
        group = _collect_group(game, games_by_id, ids_by_key, ext_id_groups, visited)
        if len(group) >= 2:
            found.append(group)
    return found


def _collect_group(
    game: Game,
    games_by_id: dict[int, Game],
    ids_by_key: dict[str, set[int]],
    ext_id_groups: dict[int, set[int]],
    visited: set[int],
) -> list[Game]:
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
    for group in find_duplicate_groups(db):
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


def consolidate_duplicate_games(db: Session) -> dict[str, int]:
    removed = 0
    merged_groups = 0
    for group in find_duplicate_groups(db):
        keeper = max(group, key=duplicate_quality_key)
        for duplicate in (item for item in group if item.id != keeper.id):
            merge_game_data(keeper, duplicate)
            _reassign_related_rows(db, keeper.id, duplicate.id)
            # The session runs with autoflush=False, so the ExternalId re-parenting
            # above is still pending here. Flush it before the Core DELETE — its
            # ON DELETE CASCADE would otherwise remove those rows first and the
            # deferred UPDATEs would raise StaleDataError at commit.
            db.flush()
            db.execute(delete(Game).where(Game.id == duplicate.id))
            removed += 1
        db.add(keeper)
        merged_groups += 1

    db.commit()
    return {"merged_groups": merged_groups, "removed": removed}


def _reassign_related_rows(db: Session, keeper_id: int, duplicate_id: int) -> None:
    # ExternalId: skip rows where (game_id=keeper, source, external_id) already exists
    existing_ext = db.scalars(select(ExternalId).where(ExternalId.game_id == keeper_id)).all()
    existing_keys = {(e.source, e.external_id) for e in existing_ext}
    for ext in db.scalars(select(ExternalId).where(ExternalId.game_id == duplicate_id)).all():
        if (ext.source, ext.external_id) in existing_keys:
            db.delete(ext)
        else:
            ext.game_id = keeper_id
    for model in (RatingSnapshot, PriceSnapshot):
        db.execute(update(model).where(model.game_id == duplicate_id).values(game_id=keeper_id))
