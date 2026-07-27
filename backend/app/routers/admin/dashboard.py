"""Traffic dashboard and the admin audit trail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...services.admin_audit import recent_admin_audit_logs
from ...services.ai_catalog_changes import recent_ai_catalog_changes
from ...services.admin_dashboard import build_admin_dashboard

router = APIRouter()


@router.get("/dashboard")
def dashboard(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> dict:
    return build_admin_dashboard(db, days)


@router.get("/audit-logs")
def get_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    action: str | None = Query(default=None, max_length=32),
    only_failures: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    """Who did what: every /admin/* request and login attempt, newest first."""
    rows = recent_admin_audit_logs(db, limit=limit, action=action, only_failures=only_failures)
    return {"logs": [_audit_row(row) for row in rows]}


@router.get("/ai-changes")
def get_ai_changes(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """Recent persisted catalog changes whose decision came from the AI chain."""
    return {"changes": recent_ai_catalog_changes(db, limit=limit)}


def _audit_row(row) -> dict[str, object]:
    return {
        "id": row.id,
        "username": row.username,
        "action": row.action,
        "method": row.method,
        "path": row.path,
        "query": row.query,
        "status_code": row.status_code,
        "success": row.success,
        "ip_address": row.ip_address,
        "user_agent": row.user_agent,
        "duration_ms": row.duration_ms,
        "created_at": row.created_at.isoformat(),
    }
