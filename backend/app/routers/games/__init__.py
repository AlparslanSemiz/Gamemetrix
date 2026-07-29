"""Public game endpoints.

  search        — GET  /api/search                          (admin RAWG-backed import)
  catalog       — GET  /api/games, /api/facets
  catalog_summary — lightweight catalog/card endpoints
  detail        — GET  /api/games/{slug} (+ similar, series, trailer)
  admin_actions — POST /api/games/{slug}/{refresh-scores,fetch-*}
"""

from fastapi import APIRouter

from . import admin_actions, catalog, catalog_summary, detail, search

router = APIRouter(tags=["games"])

for _sub_router in (
    search.router,
    catalog.router,
    catalog_summary.router,
    detail.router,
    admin_actions.router,
):
    router.include_router(_sub_router)

__all__ = ["router"]
