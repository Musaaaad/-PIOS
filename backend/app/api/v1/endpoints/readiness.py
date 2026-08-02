from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import add_audit_event
from app.core.config import get_settings
from app.core.security import Principal, require_roles
from app.db.session import get_db
from app.models.entities import (
    Organization, Site, MeasurableElement, Finding, EvidenceMeLink, EvidenceItem,
    ApplicabilityDecision, ReadinessSnapshot, ReadinessSnapshotItem,
)
from app.schemas.readiness import ApplicabilityUpsert, ApplicabilityRead, ReadinessCalculate, ReadinessSnapshotRead, ReadinessItemRead
from app.services.readiness import calculate_readiness, OPEN_FINDING_STATUSES

router = APIRouter()


def _actor_uuid(principal: Principal):
    try: return UUID(principal.user_id)
    except (ValueError, TypeError): return None


def _org_site(db: Session):
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.code == settings.organization_code))
    if not org: raise HTTPException(status_code=409, detail="Baseline organization is not seeded")
    site = db.scalar(select(Site).where(Site.organization_id == org.id, Site.code == settings.default_site_code))
    if not site: raise HTTPException(status_code=404, detail="Site not found")
    return org, site


@router.put("/measurable-elements/{me_id}/applicability", response_model=ApplicabilityRead)
def upsert_applicability(
    me_id: str, payload: ApplicabilityUpsert, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead"))],
):
    org, site = _org_site(db)
    me = db.scalar(select(MeasurableElement).where(MeasurableElement.me_id == me_id))
    if not me: raise HTTPException(status_code=404, detail="Measurable element not found")
    if payload.decision == "NotApplicable":
        active_finding = db.scalar(select(Finding.id).where(Finding.site_id == site.id, Finding.measurable_element_id == me.id, Finding.status.in_(OPEN_FINDING_STATUSES)).limit(1))
        if active_finding:
            raise HTTPException(status_code=409, detail="NotApplicable cannot bypass an active finding")
        accepted = db.scalar(select(EvidenceItem.id).join(EvidenceMeLink, EvidenceMeLink.evidence_item_id == EvidenceItem.id).where(EvidenceMeLink.measurable_element_id == me.id, EvidenceItem.status == "Accepted").limit(1))
        if accepted:
            raise HTTPException(status_code=409, detail="Resolve accepted evidence scope before marking NotApplicable")
    row = db.scalar(select(ApplicabilityDecision).where(ApplicabilityDecision.site_id == site.id, ApplicabilityDecision.measurable_element_id == me.id))
    before = None
    if row:
        before = {"decision": row.decision, "rationale": row.rationale}
        row.decision = payload.decision; row.rationale = payload.rationale
    else:
        row = ApplicabilityDecision(site_id=site.id, measurable_element_id=me.id, decision=payload.decision, rationale=payload.rationale)
        db.add(row)
    row.approved_by = _actor_uuid(principal); from datetime import datetime, timezone; row.approved_at = datetime.now(timezone.utc)
    db.flush(); add_audit_event(db, request, principal, org.id, "applicability.upsert", "ApplicabilityDecision", str(row.id), before=before, after=payload.model_dump())
    db.commit(); db.refresh(row); return row


@router.get("/applicability-decisions")
def list_applicability(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "ReadOnlyAuditor"))],
    decision: str | None = None,
):
    stmt = select(ApplicabilityDecision, MeasurableElement.me_id).join(MeasurableElement, ApplicabilityDecision.measurable_element_id == MeasurableElement.id)
    if decision: stmt = stmt.where(ApplicabilityDecision.decision == decision)
    return [{**ApplicabilityRead.model_validate(row).model_dump(mode="json"), "me_id": mid} for row, mid in db.execute(stmt.order_by(MeasurableElement.me_id)).all()]


@router.post("/readiness/snapshots/calculate", response_model=ReadinessSnapshotRead, status_code=201)
def create_snapshot(
    payload: ReadinessCalculate, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety"))],
):
    org, site = _org_site(db)
    snapshot = calculate_readiness(db, site.id, payload.period_label)
    add_audit_event(db, request, principal, org.id, "readiness.snapshot.calculate", "ReadinessSnapshot", str(snapshot.id), after={"period_label": payload.period_label, "score": snapshot.readiness_score, "overall_status": snapshot.overall_status, "critical": snapshot.critical_open_actions})
    db.commit(); db.refresh(snapshot); return snapshot


@router.get("/readiness/snapshots", response_model=list[ReadinessSnapshotRead])
def list_snapshots(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "ReadOnlyAuditor"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    _, site = _org_site(db)
    return list(db.scalars(select(ReadinessSnapshot).where(ReadinessSnapshot.site_id == site.id).order_by(ReadinessSnapshot.captured_at.desc()).limit(limit)).all())


@router.get("/readiness/current")
def current_readiness(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "ReadOnlyAuditor"))],
):
    _, site = _org_site(db)
    row = db.scalar(select(ReadinessSnapshot).where(ReadinessSnapshot.site_id == site.id).order_by(ReadinessSnapshot.captured_at.desc()).limit(1))
    if not row: raise HTTPException(status_code=404, detail="No readiness snapshot exists")
    return ReadinessSnapshotRead.model_validate(row).model_dump(mode="json")


@router.get("/readiness/snapshots/{snapshot_id}")
def snapshot_detail(
    snapshot_id: UUID, db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "ReadOnlyAuditor"))],
    state: str | None = None,
):
    row = db.get(ReadinessSnapshot, snapshot_id)
    if not row: raise HTTPException(status_code=404, detail="Readiness snapshot not found")
    stmt = select(ReadinessSnapshotItem, MeasurableElement.me_id).join(MeasurableElement, ReadinessSnapshotItem.measurable_element_id == MeasurableElement.id).where(ReadinessSnapshotItem.snapshot_id == row.id)
    if state: stmt = stmt.where(ReadinessSnapshotItem.readiness_state == state)
    items = [{**ReadinessItemRead.model_validate(x).model_dump(mode="json"), "me_id": mid} for x, mid in db.execute(stmt.order_by(MeasurableElement.me_id)).all()]
    return {"snapshot": ReadinessSnapshotRead.model_validate(row).model_dump(mode="json"), "items": items}
