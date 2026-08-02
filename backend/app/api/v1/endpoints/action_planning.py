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
    AiRecommendation,
    Capa,
    IntelligenceActionPlan,
    IntelligenceActionReview,
    IntelligenceActionTask,
    IntelligenceConversionRequest,
    IntelligenceReviewItem,
    IntelligenceReviewSession,
    MeasurableElement,
    Organization,
    Site,
)
from app.schemas.action_planning import (
    ActionPlanComplete,
    ActionPlanCreate,
    ActionPlanRead,
    ActionReviewCreate,
    ActionReviewRead,
    ActionTaskCreate,
    ActionTaskPatch,
    ActionTaskRead,
    ConversionDecision,
    ConversionRequestCreate,
    ConversionRequestRead,
    ExecuteCapa,
    ExecuteFinding,
    LifecycleComment,
    ReviewItemCreate,
    ReviewItemDecision,
    ReviewItemRead,
    ReviewSessionCreate,
    ReviewSessionRead,
)
from app.schemas.capa import CapaRead, FindingRead
from app.services.committee_governance import ensure_session_governance_ready
from app.services.action_planning import (
    add_action_review,
    add_action_task,
    add_review_item,
    complete_action_plan,
    create_action_plan,
    create_conversion_request,
    create_review_session,
    decide_conversion,
    decide_review_item,
    execute_capa,
    execute_finding,
    patch_action_task,
    start_action_plan,
    submit_action_plan,
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


def _session(db: Session, row_id: UUID):
    row = db.get(IntelligenceReviewSession, row_id)
    if not row:
        raise HTTPException(404, "Review session not found")
    return row


def _item(db: Session, row_id: UUID):
    row = db.get(IntelligenceReviewItem, row_id)
    if not row:
        raise HTTPException(404, "Review item not found")
    return row


def _plan(db: Session, row_id: UUID):
    row = db.get(IntelligenceActionPlan, row_id)
    if not row:
        raise HTTPException(404, "Action plan not found")
    return row


def _task(db: Session, row_id: UUID):
    row = db.get(IntelligenceActionTask, row_id)
    if not row:
        raise HTTPException(404, "Action task not found")
    return row


def _conversion(db: Session, row_id: UUID):
    row = db.get(IntelligenceConversionRequest, row_id)
    if not row:
        raise HTTPException(404, "Conversion request not found")
    return row


@router.post("/intelligence/action-review-sessions", response_model=ReviewSessionRead, status_code=201)
def review_session_create(
    payload: ReviewSessionCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "MedicationSafety"))],
):
    org, site = _ctx(db)
    row, created = create_review_session(db, site.id, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "intelligence.action_review.session.create", "IntelligenceReviewSession", str(row.id), after=payload.model_dump(mode="json") | {"created": created})
    db.commit(); db.refresh(row)
    return row


@router.post("/intelligence/action-review-sessions/{session_id}/open", response_model=ReviewSessionRead)
def review_session_open(session_id: UUID, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "MedicationSafety"))]):
    org, _ = _ctx(db); row = _session(db, session_id)
    ensure_session_governance_ready(db, row.id, principal.roles, require_actor=True)
    if row.status != "Draft":
        raise HTTPException(409, "Only Draft sessions can be opened")
    from app.services.action_planning import utcnow
    row.status = "Open"; row.opened_at = utcnow()
    add_audit_event(db, request, principal, org.id, "intelligence.action_review.session.open", "IntelligenceReviewSession", str(row.id), after={"status": row.status})
    db.commit(); db.refresh(row); return row


@router.post("/intelligence/action-review-sessions/{session_id}/items")
def review_item_create(session_id: UUID, payload: ReviewItemCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "MedicationSafety"))]):
    org, _ = _ctx(db); session = _session(db, session_id); recommendation = db.get(AiRecommendation, payload.recommendation_id)
    if not recommendation:
        raise HTTPException(404, "Recommendation not found")
    row, created = add_review_item(db, session, recommendation)
    add_audit_event(db, request, principal, org.id, "intelligence.action_review.item.add", "IntelligenceReviewItem", str(row.id), after={"created": created, "recommendation_id": str(recommendation.id)})
    db.commit(); db.refresh(row); return {"created": created, "item": ReviewItemRead.model_validate(row)}


@router.post("/intelligence/action-review-items/{item_id}/decision", response_model=ReviewItemRead)
def review_item_decision(item_id: UUID, payload: ReviewItemDecision, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "MedicationSafety"))]):
    org, _ = _ctx(db); row = _item(db, item_id)
    ensure_session_governance_ready(db, row.session_id, principal.roles, require_actor=True)
    decide_review_item(row, payload.decision, payload.rationale, _actor(principal))
    add_audit_event(db, request, principal, org.id, "intelligence.action_review.item.decision", "IntelligenceReviewItem", str(row.id), after=payload.model_dump())
    db.commit(); db.refresh(row); return row


@router.post("/intelligence/action-review-sessions/{session_id}/close", response_model=ReviewSessionRead)
def review_session_close(session_id: UUID, payload: LifecycleComment, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))]):
    org, _ = _ctx(db); row = _session(db, session_id)
    pending = db.scalar(select(func.count(IntelligenceReviewItem.id)).where(IntelligenceReviewItem.session_id == row.id, IntelligenceReviewItem.status != "DecisionRecorded")) or 0
    if pending:
        raise HTTPException(409, "All review items require a recorded decision")
    from app.services.action_planning import utcnow
    row.status = "Closed"; row.closed_at = utcnow()
    if payload.comment:
        row.notes = ((row.notes or "") + "\n" + payload.comment).strip()
    add_audit_event(db, request, principal, org.id, "intelligence.action_review.session.close", "IntelligenceReviewSession", str(row.id), after={"status": row.status, "comment": payload.comment})
    db.commit(); db.refresh(row); return row


@router.get("/intelligence/action-review-sessions/{session_id}")
def review_session_detail(session_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    row = _session(db, session_id)
    items = list(db.scalars(select(IntelligenceReviewItem).where(IntelligenceReviewItem.session_id == row.id).order_by(IntelligenceReviewItem.sequence)).all())
    return {"session": ReviewSessionRead.model_validate(row), "items": [ReviewItemRead.model_validate(x) for x in items]}


@router.post("/intelligence/action-plans", response_model=ActionPlanRead, status_code=201)
def action_plan_create(payload: ActionPlanCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "MEOwner"))]):
    org, site = _ctx(db); row, created = create_action_plan(db, site.id, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "intelligence.action_plan.create", "IntelligenceActionPlan", str(row.id), after=payload.model_dump(mode="json") | {"created": created})
    db.commit(); db.refresh(row); return row


@router.get("/intelligence/action-plans")
def action_plan_list(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)], status: str | None = None):
    _, site = _ctx(db); stmt = select(IntelligenceActionPlan).where(IntelligenceActionPlan.site_id == site.id)
    if status:
        stmt = stmt.where(IntelligenceActionPlan.status == status)
    rows = list(db.scalars(stmt.order_by(IntelligenceActionPlan.due_date, IntelligenceActionPlan.code)).all())
    return [ActionPlanRead.model_validate(x) for x in rows]


@router.get("/intelligence/action-plans/{plan_id}")
def action_plan_detail(plan_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    plan = _plan(db, plan_id)
    tasks = list(db.scalars(select(IntelligenceActionTask).where(IntelligenceActionTask.action_plan_id == plan.id).order_by(IntelligenceActionTask.sequence)).all())
    reviews = list(db.scalars(select(IntelligenceActionReview).where(IntelligenceActionReview.action_plan_id == plan.id).order_by(IntelligenceActionReview.reviewed_at)).all())
    conversions = list(db.scalars(select(IntelligenceConversionRequest).where(IntelligenceConversionRequest.action_plan_id == plan.id).order_by(IntelligenceConversionRequest.created_at)).all())
    return {"plan": ActionPlanRead.model_validate(plan), "tasks": [ActionTaskRead.model_validate(x) for x in tasks], "reviews": [ActionReviewRead.model_validate(x) for x in reviews], "conversion_requests": [ConversionRequestRead.model_validate(x) for x in conversions], "guardrail": "No Finding, CAPA, approval, execution or closure is performed automatically."}


@router.post("/intelligence/action-plans/{plan_id}/tasks", response_model=ActionTaskRead, status_code=201)
def action_task_create(plan_id: UUID, payload: ActionTaskCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "MEOwner", "CAPAOwner"))]):
    org, _ = _ctx(db); plan = _plan(db, plan_id); row = add_action_task(db, plan, payload)
    add_audit_event(db, request, principal, org.id, "intelligence.action_task.create", "IntelligenceActionTask", str(row.id), after=payload.model_dump(mode="json") | {"sequence": row.sequence})
    db.commit(); db.refresh(row); return row


@router.patch("/intelligence/action-tasks/{task_id}", response_model=ActionTaskRead)
def action_task_patch(task_id: UUID, payload: ActionTaskPatch, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "MEOwner", "CAPAOwner"))]):
    org, _ = _ctx(db); row = _task(db, task_id); plan = _plan(db, row.action_plan_id)
    if plan.status not in {"Approved", "InProgress"}:
        raise HTTPException(409, "Tasks can only be updated after plan approval")
    before = {"status": row.status, "evidence_reference": row.evidence_reference, "completion_note": row.completion_note}
    patch_action_task(row, payload, _actor(principal))
    if row.status in {"InProgress", "Completed"} and plan.status == "Approved":
        start_action_plan(plan)
    add_audit_event(db, request, principal, org.id, "intelligence.action_task.update", "IntelligenceActionTask", str(row.id), before=before, after=payload.model_dump(exclude_unset=True))
    db.commit(); db.refresh(row); return row


@router.post("/intelligence/action-plans/{plan_id}/submit")
def action_plan_submit(plan_id: UUID, payload: LifecycleComment, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "MEOwner"))]):
    org, _ = _ctx(db); plan = _plan(db, plan_id); validation = submit_action_plan(db, plan)
    add_audit_event(db, request, principal, org.id, "intelligence.action_plan.submit", "IntelligenceActionPlan", str(plan.id), after={"validation": validation, "comment": payload.comment})
    db.commit(); db.refresh(plan); return {"plan": ActionPlanRead.model_validate(plan), "validation": validation}


@router.post("/intelligence/action-plans/{plan_id}/reviews", response_model=ActionReviewRead, status_code=201)
def action_plan_review(plan_id: UUID, payload: ActionReviewCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "CAPAVerifier", "PharmacyDirector"))]):
    org, _ = _ctx(db); plan = _plan(db, plan_id); row = add_action_review(db, plan, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "intelligence.action_plan.review", "IntelligenceActionReview", str(row.id), after=payload.model_dump())
    db.commit(); db.refresh(row); return row


@router.post("/intelligence/action-plans/{plan_id}/start", response_model=ActionPlanRead)
def action_plan_start(plan_id: UUID, payload: LifecycleComment, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "MEOwner", "CAPAOwner"))]):
    org, _ = _ctx(db); plan = _plan(db, plan_id); start_action_plan(plan)
    add_audit_event(db, request, principal, org.id, "intelligence.action_plan.start", "IntelligenceActionPlan", str(plan.id), after={"status": plan.status, "comment": payload.comment})
    db.commit(); db.refresh(plan); return plan


@router.post("/intelligence/action-plans/{plan_id}/conversion-requests", response_model=ConversionRequestRead, status_code=201)
def conversion_create(plan_id: UUID, payload: ConversionRequestCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "MEOwner", "CAPAOwner"))]):
    org, _ = _ctx(db); plan = _plan(db, plan_id); row = create_conversion_request(db, plan, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "intelligence.conversion.request", "IntelligenceConversionRequest", str(row.id), after=payload.model_dump())
    db.commit(); db.refresh(row); return row


@router.post("/intelligence/conversion-requests/{request_id}/decision", response_model=ConversionRequestRead)
def conversion_decision(request_id: UUID, payload: ConversionDecision, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "PharmacyDirector"))]):
    org, _ = _ctx(db); row = _conversion(db, request_id); decide_conversion(row, payload.approved, payload.comment, _actor(principal))
    add_audit_event(db, request, principal, org.id, "intelligence.conversion.decision", "IntelligenceConversionRequest", str(row.id), after=payload.model_dump())
    db.commit(); db.refresh(row); return row


@router.post("/intelligence/conversion-requests/{request_id}/execute-finding", response_model=FindingRead, status_code=201)
def conversion_execute_finding(request_id: UUID, payload: ExecuteFinding, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "EvidenceReviewer"))]):
    org, _ = _ctx(db); row = _conversion(db, request_id); plan = _plan(db, row.action_plan_id); finding = execute_finding(db, row, plan, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "intelligence.conversion.execute.finding", "Finding", str(finding.id), after={"conversion_request_id": str(row.id), **payload.model_dump(mode="json")})
    db.commit(); db.refresh(finding); return finding


@router.post("/intelligence/conversion-requests/{request_id}/execute-capa", response_model=CapaRead, status_code=201)
def conversion_execute_capa(request_id: UUID, payload: ExecuteCapa, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "CAPAOwner"))]):
    org, _ = _ctx(db); row = _conversion(db, request_id); plan = _plan(db, row.action_plan_id); capa = execute_capa(db, row, plan, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "intelligence.conversion.execute.capa", "Capa", str(capa.id), after={"conversion_request_id": str(row.id), **payload.model_dump(mode="json")})
    db.commit(); db.refresh(capa); return capa


@router.post("/intelligence/action-plans/{plan_id}/complete", response_model=ActionPlanRead)
def action_plan_complete(plan_id: UUID, payload: ActionPlanComplete, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "CAPAVerifier"))]):
    org, _ = _ctx(db); plan = _plan(db, plan_id); validation = complete_action_plan(db, plan, payload.outcome_summary, _actor(principal))
    add_audit_event(db, request, principal, org.id, "intelligence.action_plan.complete", "IntelligenceActionPlan", str(plan.id), after={"validation": validation, "outcome_summary": payload.outcome_summary})
    db.commit(); db.refresh(plan); return plan


@router.get("/intelligence/action-dashboard")
def action_dashboard(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _, site = _ctx(db)
    plans = list(db.scalars(select(IntelligenceActionPlan).where(IntelligenceActionPlan.site_id == site.id)).all())
    pending_conversions = db.scalar(select(func.count(IntelligenceConversionRequest.id)).join(IntelligenceActionPlan, IntelligenceActionPlan.id == IntelligenceConversionRequest.action_plan_id).where(IntelligenceActionPlan.site_id == site.id, IntelligenceConversionRequest.status.in_(["Requested", "Approved"]))) or 0
    return {
        "site_code": site.code,
        "plans_total": len(plans),
        "by_status": {status: sum(x.status == status for x in plans) for status in ["Draft", "Submitted", "Approved", "InProgress", "Completed", "NeedsRevision", "Rejected"]},
        "pending_conversion_requests": pending_conversions,
        "linked_findings": sum(x.linked_finding_id is not None for x in plans),
        "linked_capas": sum(x.linked_capa_id is not None for x in plans),
        "guardrail": "Recommendations do not create Findings, CAPA, approvals, task completion or closure automatically.",
    }
