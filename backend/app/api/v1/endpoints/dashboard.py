from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import Principal, get_principal, require_roles
from app.db.session import get_db
from app.models.entities import (
    Organization, Site, Standard, MeasurableElement, Document, EvidenceRequest, EvidenceItem,
    Finding, Capa, CapaAction, EffectivenessCheck, ReadinessSnapshot, ReadinessSnapshotItem,
    Notification,
)

router = APIRouter()
OPEN_FINDINGS = ["Open", "Acknowledged", "CAPAOpen", "VerificationPending", "Reopened"]
OPEN_CAPAS = ["Draft", "Submitted", "Approved", "InProgress", "ImplementationComplete", "EffectivenessPending", "Reopened"]


def _org_site(db: Session):
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.code == settings.organization_code))
    if not org: raise HTTPException(status_code=409, detail="Baseline organization is not seeded")
    site = db.scalar(select(Site).where(Site.organization_id == org.id, Site.code == settings.default_site_code))
    if not site: raise HTTPException(status_code=404, detail="Site not found")
    return org, site


def _count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


@router.get("/identity/me")
def identity_me(principal: Annotated[Principal, Depends(get_principal)]):
    return {
        "user_id": principal.user_id, "roles": sorted(principal.roles), "email": principal.email,
        "display_name": principal.display_name, "site_codes": sorted(principal.site_codes),
        "auth_source": principal.auth_source,
    }


@router.get("/dashboard/overview")
def dashboard_overview(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "PharmacyDirector", "MEOwner", "CAPAOwner", "CAPAVerifier", "ReadOnlyAuditor"))],
):
    _, site = _org_site(db); now = datetime.now(timezone.utc); today = now.date()
    snapshot = db.scalar(select(ReadinessSnapshot).where(ReadinessSnapshot.site_id == site.id).order_by(ReadinessSnapshot.captured_at.desc()).limit(1))
    severity_rows = dict(db.execute(select(Finding.severity, func.count(Finding.id)).where(Finding.site_id == site.id, Finding.status.in_(OPEN_FINDINGS)).group_by(Finding.severity)).all())
    capa_rows = dict(db.execute(select(Capa.status, func.count(Capa.id)).join(Finding, Capa.finding_id == Finding.id).where(Finding.site_id == site.id).group_by(Capa.status)).all())
    return {
        "site": {"code": site.code, "name_ar": site.name_ar, "name_en": site.name_en},
        "readiness": None if not snapshot else {
            "snapshot_id": str(snapshot.id), "period_label": snapshot.period_label,
            "score": snapshot.readiness_score, "overall_status": snapshot.overall_status,
            "critical_open_actions": snapshot.critical_open_actions,
            "accepted": snapshot.evidence_sufficient_me, "partial": snapshot.evidence_partial_me,
            "missing": snapshot.evidence_missing_me, "esr_status": snapshot.esr_status,
        },
        "findings": {"open_total": sum(severity_rows.values()), "by_severity": severity_rows},
        "capas": {"by_status": capa_rows, "overdue": _count(db, select(func.count(Capa.id)).join(Finding, Capa.finding_id == Finding.id).where(Finding.site_id == site.id, Capa.due_date < today, Capa.status.in_(OPEN_CAPAS)))},
        "evidence": {
            "overdue_requests": _count(db, select(func.count(EvidenceRequest.id)).where(EvidenceRequest.due_at < now, EvidenceRequest.status.in_(["Requested", "Collecting", "Returned"]))),
            "under_review": _count(db, select(func.count(EvidenceItem.id)).where(EvidenceItem.site_id == site.id, EvidenceItem.status.in_(["Submitted", "UnderReview"]))),
        },
        "documents": dict(db.execute(select(Document.lifecycle_status, func.count(Document.id)).where(Document.organization_id == site.organization_id).group_by(Document.lifecycle_status)).all()),
        "notifications": {
            "unread": _count(db, select(func.count(Notification.id)).where(Notification.site_id == site.id, Notification.status == "Unread")),
            "critical": _count(db, select(func.count(Notification.id)).where(Notification.site_id == site.id, Notification.status != "Archived", Notification.severity == "Critical")),
        },
        "generated_at": now,
    }


@router.get("/dashboard/standards")
def standards_dashboard(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "PharmacyDirector", "ReadOnlyAuditor"))],
):
    _, site = _org_site(db)
    snapshot = db.scalar(select(ReadinessSnapshot).where(ReadinessSnapshot.site_id == site.id).order_by(ReadinessSnapshot.captured_at.desc()).limit(1))
    if not snapshot: return {"snapshot": None, "standards": []}
    rows = db.execute(select(Standard.code, ReadinessSnapshotItem.readiness_state, func.count(ReadinessSnapshotItem.id)).join(
        MeasurableElement, MeasurableElement.standard_id == Standard.id
    ).join(ReadinessSnapshotItem, ReadinessSnapshotItem.measurable_element_id == MeasurableElement.id).where(
        ReadinessSnapshotItem.snapshot_id == snapshot.id
    ).group_by(Standard.code, ReadinessSnapshotItem.readiness_state)).all()
    grouped = {}
    for code, state, count in rows:
        grouped.setdefault(code, {})[state] = count
    return {"snapshot": {"id": str(snapshot.id), "period_label": snapshot.period_label}, "standards": [{"standard": k, "states": v, "total": sum(v.values())} for k, v in sorted(grouped.items(), key=lambda x: int(x[0].split('.')[1]))]}


@router.get("/worklists/my")
def my_worklist(
    db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(get_principal)],
    limit: Annotated[int, Query(ge=1, le=300)] = 100,
):
    _, site = _org_site(db); now = datetime.now(timezone.utc); today = now.date(); tasks = []
    def is_overdue(value):
        if value is None: return False
        if isinstance(value, datetime) and value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
        return value < now
    roles = principal.roles

    if roles.intersection({"SystemAdmin", "EvidenceCollector", "EvidenceReviewer", "AccreditationLead"}):
        rows = db.execute(select(EvidenceRequest, MeasurableElement.me_id).join(MeasurableElement, EvidenceRequest.measurable_element_id == MeasurableElement.id).where(EvidenceRequest.status.in_(["Requested", "Collecting", "Submitted", "Returned"])).order_by(EvidenceRequest.due_at.asc()).limit(limit)).all()
        for row, me_id in rows:
            tasks.append({"task_type":"EvidenceRequest","id":str(row.id),"title":f"دليل {me_id} - {row.tool_code}","status":row.status,"severity":"Warning" if is_overdue(row.due_at) else "Normal","due_at":row.due_at,"href":f"#/evidence/{row.id}"})

    if roles.intersection({"SystemAdmin", "MEOwner", "MedicationSafety", "AccreditationLead", "CAPAOwner", "CAPAVerifier"}):
        rows = db.execute(select(Finding, MeasurableElement.me_id).join(MeasurableElement, Finding.measurable_element_id == MeasurableElement.id).where(Finding.site_id == site.id, Finding.status.in_(OPEN_FINDINGS)).order_by(Finding.due_date.asc()).limit(limit)).all()
        for row, me_id in rows:
            tasks.append({"task_type":"Finding","id":str(row.id),"title":f"{row.severity} - {me_id}","status":row.status,"severity":"Critical" if row.severity == "P0" else row.severity,"due_at":row.due_date,"href":f"#/findings/{row.id}"})

    if roles.intersection({"SystemAdmin", "CAPAOwner", "CAPAVerifier", "MedicationSafety", "AccreditationLead"}):
        rows = db.execute(select(Capa, MeasurableElement.me_id, Finding.severity).join(Finding, Capa.finding_id == Finding.id).join(MeasurableElement, Finding.measurable_element_id == MeasurableElement.id).where(Finding.site_id == site.id, Capa.status.in_(OPEN_CAPAS)).order_by(Capa.due_date.asc()).limit(limit)).all()
        for row, me_id, severity in rows:
            tasks.append({"task_type":"CAPA","id":str(row.id),"title":f"CAPA {me_id}: {row.title}","status":row.status,"severity":"Critical" if severity == "P0" else severity,"due_at":row.due_date,"href":f"#/capas/{row.id}"})

    tasks.sort(key=lambda x: (0 if x["severity"] == "Critical" else 1, str(x.get("due_at") or "9999")))
    return {"principal": {"user_id": principal.user_id, "roles": sorted(roles)}, "total": len(tasks), "items": tasks[:limit]}
