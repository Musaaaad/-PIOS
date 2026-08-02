from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import add_audit_event
from app.core.config import get_settings
from app.core.security import Principal, get_principal, require_roles
from app.db.session import get_db
from app.models.entities import Organization, Site, Notification
from app.schemas.sprint4 import NotificationPatch, NotificationRead
from app.services.notifications import refresh_notifications

router = APIRouter()


def _org_site(db: Session):
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.code == settings.organization_code))
    if not org: raise HTTPException(status_code=409, detail="Baseline organization is not seeded")
    site = db.scalar(select(Site).where(Site.organization_id == org.id, Site.code == settings.default_site_code))
    if not site: raise HTTPException(status_code=404, detail="Site not found")
    return org, site


@router.post("/notifications/refresh")
def refresh_alerts(
    request: Request, db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety"))],
):
    org, site = _org_site(db); result = refresh_notifications(db, site)
    add_audit_event(db, request, principal, org.id, "notifications.refresh", "Site", str(site.id), after=result)
    db.commit(); return result


@router.get("/notifications", response_model=list[NotificationRead])
def list_notifications(
    db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)],
    status: str | None = None, severity: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    _, site = _org_site(db)
    stmt = select(Notification).where(Notification.site_id == site.id)
    if status: stmt = stmt.where(Notification.status == status)
    if severity: stmt = stmt.where(Notification.severity == severity)
    return list(db.scalars(stmt.order_by(Notification.created_at.desc()).limit(limit)).all())


@router.get("/notifications/summary")
def notification_summary(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _, site = _org_site(db)
    rows = db.execute(select(Notification.status, Notification.severity, func.count(Notification.id)).where(Notification.site_id == site.id).group_by(Notification.status, Notification.severity)).all()
    return {"site": site.code, "groups": [{"status": s, "severity": sev, "count": n} for s, sev, n in rows]}


@router.patch("/notifications/{notification_id}", response_model=NotificationRead)
def patch_notification(
    notification_id: UUID, payload: NotificationPatch, request: Request,
    db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(get_principal)],
):
    org, site = _org_site(db); row = db.get(Notification, notification_id)
    if not row or row.site_id != site.id: raise HTTPException(status_code=404, detail="Notification not found")
    before = row.status; row.status = payload.status
    now = datetime.now(timezone.utc)
    if payload.status == "Read": row.read_at = now
    elif payload.status == "Archived": row.archived_at = now
    elif payload.status == "Unread": row.read_at = None; row.archived_at = None
    add_audit_event(db, request, principal, org.id, "notification.update", "Notification", str(row.id), before={"status":before}, after={"status":row.status})
    db.commit(); db.refresh(row); return row
