"""Top-level refresh: fetch every applicable source, rescore, persist."""

import asyncio
from datetime import UTC, datetime

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import ExternalId, Game
from .fetching import build_fetch_tasks
from .persistence import persist_source_records
from .ranking import update_derived_scores
from .scoring import calculate_metrix_score
from .serialization import merge_source_scores

_MIN_EXTERNAL_ID_CONFIDENCE = 0.8


def _trusted_external_ids(db: Session, game: Game) -> dict[str, str]:
    rows = db.scalars(
        select(ExternalId)
        .where(
            ExternalId.game_id == game.id,
            ExternalId.is_primary.is_(True),
            ExternalId.confidence >= _MIN_EXTERNAL_ID_CONFIDENCE,
        )
        .order_by(ExternalId.confidence.desc(), ExternalId.updated_at.desc())
    ).all()
    external_ids: dict[str, str] = {}
    for row in rows:
        external_ids.setdefault(row.source, row.external_id)
    return external_ids


async def refresh_game_sources(
    db: Session,
    game: Game,
    *,
    sources: Sequence[str] | None = None,
    force: bool = False,
    include_support: bool = True,
    include_rawg_fallback: bool = True,
    refresh_metadata: bool = True,
) -> Game:
    fresh_scores = list(await asyncio.gather(*build_fetch_tasks(
        game,
        external_ids=_trusted_external_ids(db, game),
        sources=sources,
        force=force,
        include_support=include_support,
        include_rawg_fallback=include_rawg_fallback,
    )))

    if refresh_metadata:
        from ...services.metadata import enrich_game_summary, fix_game_year
        await asyncio.gather(fix_game_year(game), enrich_game_summary(game))

    game.source_scores = merge_source_scores(game.source_scores, fresh_scores)
    game.metrix_score = calculate_metrix_score(game.source_scores)
    game.ratings_refreshed_at = datetime.now(UTC)
    update_derived_scores(game, fresh_scores)
    persist_source_records(db, game, fresh_scores)

    from ...services.seo import refresh_game_seo_state
    refresh_game_seo_state(game, content_updated=True)
    from ...services.completeness import refresh_data_complete
    refresh_data_complete(game)

    db.add(game)
    db.commit()
    db.refresh(game)
    return game
