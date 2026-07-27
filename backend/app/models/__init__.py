"""ORM models, grouped by domain.

  catalog   — Game and the source data attached to it
  accounts  — users, sessions, collections, notification state
  analytics — visit and product-analytics events
  ops       — provider budgets, admin audit trail, data-fill runs

Every model is re-exported here, so `from ..models import Game` keeps working.
Computed Game properties delegate to `game_signals.py`; classification lives in
`content_type.py`. Keep this package to table definitions only.
"""

from .accounts import (
    AccountSession,
    AccountToken,
    NotificationDelivery,
    OAuthIdentity,
    User,
    UserAlertState,
    UserCollection,
    UserPreference,
)
from .analytics import AnalyticsEvent, VisitEvent
from .catalog import ExternalId, Game, PriceSnapshot, RatingSnapshot, SourceSnapshot
from .ops import (
    AdminAuditLog,
    AiCatalogChange,
    ApiRequestBudget,
    ApiRequestWindow,
    CatalogQualityReview,
    CatalogSyncState,
    DataFillRun,
    JobRun,
)

__all__ = [
    "AccountSession",
    "AccountToken",
    "AdminAuditLog",
    "AiCatalogChange",
    "AnalyticsEvent",
    "ApiRequestBudget",
    "ApiRequestWindow",
    "CatalogQualityReview",
    "CatalogSyncState",
    "DataFillRun",
    "ExternalId",
    "Game",
    "JobRun",
    "NotificationDelivery",
    "OAuthIdentity",
    "PriceSnapshot",
    "RatingSnapshot",
    "SourceSnapshot",
    "User",
    "UserAlertState",
    "UserCollection",
    "UserPreference",
    "VisitEvent",
]
