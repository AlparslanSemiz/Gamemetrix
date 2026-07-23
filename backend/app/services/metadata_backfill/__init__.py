"""Rate-limited metadata backfill for existing games.

Complements score refreshes by filling cover art, descriptions, developer /
publisher, platform / genre gaps, screenshots, system requirements, website
URLs and external IDs in small periodic batches.

Layering: sanitize (field shape) → gaps (what to fix, when) → persistence
(external ids / snapshots) → apply (write fields) → sources (per-provider
refresh + per-game orchestration) → batch (the loop).
"""

from .batch import METADATA_BACKFILL_LOCK, metadata_backfill_batch
from .gaps import (
    game_needs_metadata_backfill,
    metadata_backfill_candidates,
    metadata_gap_score,
)
from .persistence import upsert_external_id
from .sanitize import safe_url, system_requirements_need_repair
from .sources import refresh_game_metadata

__all__ = [
    "METADATA_BACKFILL_LOCK",
    "game_needs_metadata_backfill",
    "metadata_backfill_batch",
    "metadata_backfill_candidates",
    "metadata_gap_score",
    "refresh_game_metadata",
    "safe_url",
    "system_requirements_need_repair",
    "upsert_external_id",
]
