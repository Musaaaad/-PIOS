from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import add_audit_event
from app.core.config import get_settings
from app.core.security import Principal, get_principal, require_roles
from app.db.session import get_db
from app.models.entities import (
    CommitteeConflictDeclaration,
    CommitteeMembership,
    CommitteeSessionAttendance,
    DecisionMetricsSnapshot,
    DecisionQualityReview,
    DecisionSlaPolicy,
    InstitutionalCommittee,
    IntelligenceReviewItem,
    IntelligenceReviewSession,
    Organization,
    SessionGovernance,
    Site,
)
from app.schemas.committee_governance import (
    AttendanceRead,
    AttendanceUpsert,
    CommitteeCreate,
    CommitteeRead,
    ConflictDeclarationCreate,
    ConflictDeclarationRead,
    ConflictResolve,
    DecisionQualityReviewCreate,
    DecisionQualityReviewRead,
    GovernanceBind,
    GovernanceRead,
    MembershipCreate,
    MembershipPatch,
    MembershipRead,
    MetricsSnapshotCreate,
    MetricsSnapshotRead,
    SlaPolicyCreate,
    SlaPolicyRead,
)
from app.services.committee_governance import (
    activate_committee,
    add_membership,
    add_quality_review,
    bind_session,
    create_committee,
    create_sla_policy,
    declare_conflict,
    evaluate_governance,
    generate_metrics_snapshot,
    patch_membership,
    resolve_conflict,
    upsert_attendance,
)

router = APIRouter()


def _actor(principal: Principal):
    try:
        return UUID(principal.user_id)
    except (ValueError, TypeError):
        return None


def _ctx(db: Session):
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.code == settings.organization_code))
    if not org:
        raise HTTPException(409, "Baseline organization is not seeded")
    site = db.scalar(select(Site).where(Site.organization_id == org.id, Site.code == settings.default_site_code))
    if not site:
        raise HTTPException(404, "Site not found")
    return org, site


def _committee(db: Session, row_id: UUID):
    row = db.get(InstitutionalCommittee, row_id)
    if not row:
        raise HTTPException(404, "Committee not found")
    return row


def _membership(db: Session, row_id: UUID):
    row = db.get(CommitteeMembership, row_id)
    if not row:
        raise HTTPException(404, "Committee membership not found")
    return row


def _governance(db: Session, row_id: UUID):
    row = db.get(SessionGovernance, row_id)
    if not row:
        raise HTTPException(404, "Session governance record not found")
    return row


@router.post("/institutional-governance/committees", response_model=CommitteeRead, status_code=201)
def committee_create(payload: CommitteeCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))]):
    org, site = _ctx(db)
    row, created = create_committee(db, site.id, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "committee.create", "InstitutionalCommittee", str(row.id), after=payload.model_dump(mode="json") | {"created": created})
    db.commit(); db.refresh(row); return row


@router.get("/institutional-governance/committees")
def committee_list(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _, site = _ctx(db)
    rows = list(db.scalars(select(InstitutionalCommittee).where(InstitutionalCommittee.site_id == site.id).order_by(InstitutionalCommittee.code)).all())
    return {"items": [CommitteeRead.model_validate(x) for x in rows], "total": len(rows)}


@router.post("/institutional-governance/committees/{committee_id}/members", response_model=MembershipRead, status_code=201)
def membership_create(committee_id: UUID, payload: MembershipCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))]):
    org, _ = _ctx(db); committee = _committee(db, committee_id)
    row, created = add_membership(db, committee, payload)
    add_audit_event(db, request, principal, org.id, "committee.membership.create", "CommitteeMembership", str(row.id), after=payload.model_dump(mode="json") | {"created": created})
    db.commit(); db.refresh(row); return row


@router.patch("/institutional-governance/members/{membership_id}", response_model=MembershipRead)
def membership_update(membership_id: UUID, payload: MembershipPatch, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))]):
    org, _ = _ctx(db); row = _membership(db, membership_id)
    before = {k: getattr(row, k) for k in payload.model_dump(exclude_unset=True)}
    patch_membership(row, payload)
    add_audit_event(db, request, principal, org.id, "committee.membership.update", "CommitteeMembership", str(row.id), before=before, after=payload.model_dump(exclude_unset=True))
    db.commit(); db.refresh(row); return row


@router.post("/institutional-governance/committees/{committee_id}/activate", response_model=CommitteeRead)
def committee_activate(committee_id: UUID, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "PharmacyDirector"))]):
    org, _ = _ctx(db); row = _committee(db, committee_id); validation = activate_committee(db, row, _actor(principal))
    add_audit_event(db, request, principal, org.id, "committee.activate", "InstitutionalCommittee", str(row.id), after={"status": row.status, "validation": validation})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-governance/review-sessions/{session_id}/bind", response_model=GovernanceRead, status_code=201)
def governance_bind(session_id: UUID, payload: GovernanceBind, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))]):
    org, _ = _ctx(db); session = db.get(IntelligenceReviewSession, session_id); committee = _committee(db, payload.committee_id)
    if not session: raise HTTPException(404, "Review session not found")
    row, created = bind_session(db, session, committee)
    add_audit_event(db, request, principal, org.id, "committee.session.bind", "SessionGovernance", str(row.id), after={"committee_id": str(committee.id), "created": created})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-governance/session-governance/{governance_id}/attendance", response_model=AttendanceRead)
def attendance_record(governance_id: UUID, payload: AttendanceUpsert, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "MedicationSafety"))]):
    org, _ = _ctx(db); governance = _governance(db, governance_id)
    row = upsert_attendance(db, governance, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "committee.attendance.record", "CommitteeSessionAttendance", str(row.id), after=payload.model_dump(mode="json"))
    db.commit(); db.refresh(row); return row


@router.post("/institutional-governance/session-governance/{governance_id}/conflicts", response_model=ConflictDeclarationRead)
def conflict_declare(governance_id: UUID, payload: ConflictDeclarationCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "MedicationSafety", "MEOwner"))]):
    org, _ = _ctx(db); governance = _governance(db, governance_id)
    row = declare_conflict(db, governance, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "committee.conflict.declare", "CommitteeConflictDeclaration", str(row.id), after=payload.model_dump(mode="json") | {"status": row.status})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-governance/conflicts/{conflict_id}/resolve", response_model=ConflictDeclarationRead)
def conflict_resolve(conflict_id: UUID, payload: ConflictResolve, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))]):
    org, _ = _ctx(db); row = db.get(CommitteeConflictDeclaration, conflict_id)
    if not row: raise HTTPException(404, "Conflict declaration not found")
    resolve_conflict(row, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "committee.conflict.resolve", "CommitteeConflictDeclaration", str(row.id), after=payload.model_dump() | {"status": row.status})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-governance/session-governance/{governance_id}/evaluate")
def governance_evaluate(governance_id: UUID, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "MedicationSafety"))]):
    org, _ = _ctx(db); row = _governance(db, governance_id); evaluation = evaluate_governance(db, row, _actor(principal))
    add_audit_event(db, request, principal, org.id, "committee.governance.evaluate", "SessionGovernance", str(row.id), after=evaluation)
    db.commit(); db.refresh(row); return {"governance": GovernanceRead.model_validate(row), "evaluation": evaluation}


@router.get("/institutional-governance/session-governance/{governance_id}")
def governance_detail(governance_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    row = _governance(db, governance_id)
    attendance = list(db.scalars(select(CommitteeSessionAttendance).where(CommitteeSessionAttendance.governance_id == row.id)).all())
    conflicts = list(db.scalars(select(CommitteeConflictDeclaration).where(CommitteeConflictDeclaration.governance_id == row.id)).all())
    return {"governance": GovernanceRead.model_validate(row), "attendance": [AttendanceRead.model_validate(x) for x in attendance], "conflicts": [ConflictDeclarationRead.model_validate(x) for x in conflicts]}


@router.post("/institutional-governance/sla-policies", response_model=SlaPolicyRead, status_code=201)
def sla_policy_create(payload: SlaPolicyCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))]):
    org, site = _ctx(db); row, created = create_sla_policy(db, site.id, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "committee.sla.create", "DecisionSlaPolicy", str(row.id), after=payload.model_dump() | {"created": created})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-governance/review-items/{item_id}/quality-review", response_model=DecisionQualityReviewRead, status_code=201)
def quality_review_create(item_id: UUID, payload: DecisionQualityReviewCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "ReadOnlyAuditor", "CAPAVerifier", "PharmacyDirector"))]):
    org, _ = _ctx(db); item = db.get(IntelligenceReviewItem, item_id)
    if not item: raise HTTPException(404, "Review item not found")
    row = add_quality_review(db, item, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "committee.decision.quality_review", "DecisionQualityReview", str(row.id), after=payload.model_dump() | {"quality_score": row.quality_score, "outcome": row.outcome})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-governance/metrics-snapshots", response_model=MetricsSnapshotRead, status_code=201)
def metrics_snapshot_create(payload: MetricsSnapshotCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "ReadOnlyAuditor"))]):
    org, site = _ctx(db); row, created = generate_metrics_snapshot(db, site.id, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "committee.metrics.generate", "DecisionMetricsSnapshot", str(row.id), after=payload.model_dump(mode="json") | {"created": created, "summary": row.summary_json})
    db.commit(); db.refresh(row); return row


@router.get("/institutional-governance/dashboard")
def governance_dashboard(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _, site = _ctx(db)
    committees = list(db.scalars(select(InstitutionalCommittee).where(InstitutionalCommittee.site_id == site.id)).all())
    session_ids = list(db.scalars(select(IntelligenceReviewSession.id).where(IntelligenceReviewSession.site_id == site.id)).all())
    governance_rows = list(db.scalars(select(SessionGovernance).where(SessionGovernance.review_session_id.in_(session_ids))).all()) if session_ids else []
    quality = list(db.scalars(select(DecisionQualityReview).join(IntelligenceReviewItem, IntelligenceReviewItem.id == DecisionQualityReview.review_item_id).where(IntelligenceReviewItem.session_id.in_(session_ids))).all()) if session_ids else []
    latest = db.scalar(select(DecisionMetricsSnapshot).where(DecisionMetricsSnapshot.site_id == site.id).order_by(DecisionMetricsSnapshot.generated_at.desc()).limit(1))
    return {
        "site_code": site.code,
        "committees_total": len(committees),
        "active_committees": sum(x.status == "Active" for x in committees),
        "governed_sessions": len(governance_rows),
        "ready_sessions": sum(x.status == "Ready" for x in governance_rows),
        "blocked_sessions": sum(x.status == "Blocked" for x in governance_rows),
        "unresolved_conflicts": sum(x.unresolved_conflicts for x in governance_rows),
        "quality_reviews": len(quality),
        "average_quality_score": round(sum(x.quality_score for x in quality) / len(quality), 1) if quality else None,
        "latest_metrics": MetricsSnapshotRead.model_validate(latest) if latest else None,
        "guardrail": "Decision analytics assess governance timeliness and documentation quality; they do not approve compliance or replace human authority.",
    }
