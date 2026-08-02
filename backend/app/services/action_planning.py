from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AiRecommendation,
    Capa,
    Finding,
    IntelligenceActionPlan,
    IntelligenceActionReview,
    IntelligenceActionTask,
    IntelligenceConversionRequest,
    IntelligenceReviewItem,
    IntelligenceReviewSession,
    MeasurableElement,
)


def utcnow():
    return datetime.now(timezone.utc)


def create_review_session(db: Session, site_id, payload, actor_id=None):
    existing = db.scalar(
        select(IntelligenceReviewSession).where(
            IntelligenceReviewSession.site_id == site_id,
            IntelligenceReviewSession.code == payload.code,
        )
    )
    if existing:
        return existing, False
    row = IntelligenceReviewSession(
        site_id=site_id,
        code=payload.code,
        title=payload.title,
        scheduled_at=payload.scheduled_at,
        chair_role_code=payload.chair_role_code,
        quorum_required=payload.quorum_required,
        notes=payload.notes,
        status="Draft",
        created_by=actor_id,
    )
    db.add(row)
    db.flush()
    return row, True


def add_review_item(db: Session, session: IntelligenceReviewSession, recommendation: AiRecommendation):
    if session.status not in {"Draft", "Open"}:
        raise HTTPException(409, "Review items cannot be added after the session is closed")
    if recommendation.status != "HumanApprovedForPlanning":
        raise HTTPException(409, "Recommendation must be human-approved before committee review")
    existing = db.scalar(
        select(IntelligenceReviewItem).where(
            IntelligenceReviewItem.session_id == session.id,
            IntelligenceReviewItem.recommendation_id == recommendation.id,
        )
    )
    if existing:
        return existing, False
    sequence = (
        db.scalar(
            select(func.max(IntelligenceReviewItem.sequence)).where(
                IntelligenceReviewItem.session_id == session.id
            )
        )
        or 0
    ) + 1
    row = IntelligenceReviewItem(
        session_id=session.id,
        recommendation_id=recommendation.id,
        sequence=sequence,
        status="Pending",
    )
    db.add(row)
    db.flush()
    return row, True


def decide_review_item(item: IntelligenceReviewItem, decision: str, rationale: str, actor_id=None):
    if item.status == "DecisionRecorded":
        raise HTTPException(409, "Decision has already been recorded")
    item.decision = decision
    item.rationale = rationale
    item.status = "DecisionRecorded"
    item.decided_by = actor_id
    item.decided_at = utcnow()
    return item


def create_action_plan(db: Session, site_id, payload, actor_id=None):
    recommendation = db.get(AiRecommendation, payload.recommendation_id)
    if not recommendation or recommendation.site_id != site_id:
        raise HTTPException(404, "Recommendation not found")
    if recommendation.status != "HumanApprovedForPlanning":
        raise HTTPException(409, "Recommendation must be human-approved before action planning")
    adopted = db.scalar(
        select(IntelligenceReviewItem).where(
            IntelligenceReviewItem.recommendation_id == recommendation.id,
            IntelligenceReviewItem.decision == "AdoptForPlanning",
        ).order_by(IntelligenceReviewItem.decided_at.desc()).limit(1)
    )
    if not adopted:
        raise HTTPException(409, "A recorded AdoptForPlanning decision is required")
    existing = db.scalar(
        select(IntelligenceActionPlan).where(
            IntelligenceActionPlan.recommendation_id == recommendation.id
        )
    )
    if existing:
        return existing, False
    row = IntelligenceActionPlan(
        site_id=site_id,
        recommendation_id=recommendation.id,
        measurable_element_id=recommendation.measurable_element_id,
        code=payload.code,
        title=payload.title,
        objective=payload.objective,
        owner_role_code=payload.owner_role_code,
        verifier_role_code=payload.verifier_role_code,
        due_date=payload.due_date,
        status="Draft",
        human_authorized=True,
        created_by=actor_id,
    )
    db.add(row)
    db.flush()
    return row, True


def add_action_task(db: Session, plan: IntelligenceActionPlan, payload):
    if plan.status not in {"Draft", "NeedsRevision", "Approved", "InProgress"}:
        raise HTTPException(409, "Tasks cannot be added in the current action-plan status")
    sequence = (
        db.scalar(
            select(func.max(IntelligenceActionTask.sequence)).where(
                IntelligenceActionTask.action_plan_id == plan.id
            )
        )
        or 0
    ) + 1
    row = IntelligenceActionTask(
        action_plan_id=plan.id,
        sequence=sequence,
        action=payload.action,
        owner_role_code=payload.owner_role_code,
        due_date=payload.due_date,
        status="Open",
    )
    db.add(row)
    db.flush()
    return row


def submit_action_plan(db: Session, plan: IntelligenceActionPlan):
    if plan.status not in {"Draft", "NeedsRevision"}:
        raise HTTPException(409, "Only Draft or NeedsRevision action plans can be submitted")
    tasks = list(
        db.scalars(
            select(IntelligenceActionTask).where(
                IntelligenceActionTask.action_plan_id == plan.id,
                IntelligenceActionTask.status != "Cancelled",
            )
        ).all()
    )
    if not tasks:
        raise HTTPException(409, "At least one active task is required")
    if any(not task.owner_role_code or task.due_date is None for task in tasks):
        raise HTTPException(409, "Every task requires an owner role and due date")
    plan.status = "Submitted"
    plan.submitted_at = utcnow()
    return {"task_count": len(tasks), "human_authorized": plan.human_authorized}


def add_action_review(db: Session, plan: IntelligenceActionPlan, payload, actor_id=None):
    if payload.review_type == "Approval" and plan.status not in {"Submitted", "NeedsRevision"}:
        raise HTTPException(409, "Approval review requires a submitted action plan")
    if payload.review_type == "CompletionVerification" and plan.status != "InProgress":
        raise HTTPException(409, "Completion verification requires an InProgress action plan")
    row = IntelligenceActionReview(
        action_plan_id=plan.id,
        review_type=payload.review_type,
        decision=payload.decision,
        comment=payload.comment,
        reviewer_role_code=payload.reviewer_role_code,
        reviewed_by=actor_id,
        reviewed_at=utcnow(),
    )
    db.add(row)
    db.flush()
    if payload.review_type == "Approval":
        if payload.decision == "Approve":
            plan.status = "Approved"
            plan.approved_by = actor_id
            plan.approved_at = utcnow()
        elif payload.decision == "NeedsRevision":
            plan.status = "NeedsRevision"
        else:
            plan.status = "Rejected"
    return row


def start_action_plan(plan: IntelligenceActionPlan):
    if plan.status != "Approved":
        raise HTTPException(409, "Action plan must be approved before work starts")
    plan.status = "InProgress"
    plan.started_at = utcnow()
    return plan


def patch_action_task(task: IntelligenceActionTask, payload, actor_id=None):
    if payload.status is not None:
        task.status = payload.status
        if payload.status == "Completed":
            task.completed_at = utcnow()
            task.completed_by = actor_id
        elif payload.status in {"Open", "InProgress"}:
            task.completed_at = None
            task.completed_by = None
    if payload.evidence_reference is not None:
        task.evidence_reference = payload.evidence_reference
    if payload.completion_note is not None:
        task.completion_note = payload.completion_note
    return task


def create_conversion_request(db: Session, plan: IntelligenceActionPlan, payload, actor_id=None):
    if plan.status not in {"Approved", "InProgress", "Completed"}:
        raise HTTPException(409, "Conversion requests require an approved action plan")
    if payload.target_type == "CAPA" and plan.linked_finding_id is None:
        raise HTTPException(409, "A linked Finding is required before requesting CAPA creation")
    row = IntelligenceConversionRequest(
        action_plan_id=plan.id,
        target_type=payload.target_type,
        severity=payload.severity,
        rationale=payload.rationale,
        status="Requested",
        requested_by=actor_id,
        requested_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def decide_conversion(row: IntelligenceConversionRequest, approved: bool, comment: str, actor_id=None):
    if row.status != "Requested":
        raise HTTPException(409, "Only Requested conversion requests can be decided")
    row.status = "Approved" if approved else "Rejected"
    row.approved_by = actor_id
    row.approved_at = utcnow()
    row.execution_note = comment
    return row


def execute_finding(db: Session, request: IntelligenceConversionRequest, plan: IntelligenceActionPlan, payload, actor_id=None):
    if request.target_type != "Finding" or request.status != "Approved":
        raise HTTPException(409, "An approved Finding conversion request is required")
    if request.executed_entity_id:
        raise HTTPException(409, "Conversion request has already been executed")
    me = db.get(MeasurableElement, plan.measurable_element_id) if plan.measurable_element_id else None
    if not me:
        raise HTTPException(409, "Action plan is not linked to a measurable element")
    severity = "P0" if me.esr else (request.severity or "P1")
    finding = Finding(
        site_id=plan.site_id,
        measurable_element_id=me.id,
        source_type="IntelligenceReview",
        criterion=payload.criterion,
        severity=severity,
        problem_statement=payload.problem_statement,
        owner_role_code=payload.owner_role_code,
        due_date=payload.due_date,
        status="Open",
    )
    db.add(finding)
    db.flush()
    plan.linked_finding_id = finding.id
    request.status = "Executed"
    request.executed_by = actor_id
    request.executed_at = utcnow()
    request.executed_entity_id = str(finding.id)
    request.execution_note = "Finding created by an explicit authorized human action."
    return finding


def execute_capa(db: Session, request: IntelligenceConversionRequest, plan: IntelligenceActionPlan, payload, actor_id=None):
    if request.target_type != "CAPA" or request.status != "Approved":
        raise HTTPException(409, "An approved CAPA conversion request is required")
    if request.executed_entity_id:
        raise HTTPException(409, "Conversion request has already been executed")
    if not plan.linked_finding_id:
        raise HTTPException(409, "A linked Finding is required")
    existing = db.scalar(select(Capa).where(Capa.finding_id == plan.linked_finding_id))
    if existing:
        raise HTTPException(409, "The linked Finding already has a CAPA")
    capa = Capa(
        finding_id=plan.linked_finding_id,
        title=payload.title,
        owner_role_code=payload.owner_role_code,
        verifier_role_code=payload.verifier_role_code,
        due_date=payload.due_date,
        status="Draft",
        root_cause=payload.root_cause,
        action_plan=payload.action_plan,
    )
    db.add(capa)
    db.flush()
    finding = db.get(Finding, plan.linked_finding_id)
    if finding:
        finding.status = "CAPAOpen"
    plan.linked_capa_id = capa.id
    request.status = "Executed"
    request.executed_by = actor_id
    request.executed_at = utcnow()
    request.executed_entity_id = str(capa.id)
    request.execution_note = "CAPA draft created by an explicit authorized human action."
    return capa


def complete_action_plan(db: Session, plan: IntelligenceActionPlan, outcome_summary: str, actor_id=None):
    if plan.status != "InProgress":
        raise HTTPException(409, "Only an InProgress action plan can be completed")
    tasks = list(
        db.scalars(
            select(IntelligenceActionTask).where(
                IntelligenceActionTask.action_plan_id == plan.id,
                IntelligenceActionTask.status != "Cancelled",
            )
        ).all()
    )
    if not tasks or any(task.status != "Completed" for task in tasks):
        raise HTTPException(409, "All active tasks must be completed")
    verification = db.scalar(
        select(IntelligenceActionReview).where(
            IntelligenceActionReview.action_plan_id == plan.id,
            IntelligenceActionReview.review_type == "CompletionVerification",
            IntelligenceActionReview.decision == "Approve",
        ).order_by(IntelligenceActionReview.reviewed_at.desc()).limit(1)
    )
    if not verification:
        raise HTTPException(409, "Independent completion verification is required")
    pending = db.scalar(
        select(func.count(IntelligenceConversionRequest.id)).where(
            IntelligenceConversionRequest.action_plan_id == plan.id,
            IntelligenceConversionRequest.status.in_(["Requested", "Approved"]),
        )
    ) or 0
    if pending:
        raise HTTPException(409, "Pending conversion requests must be decided or executed")
    plan.status = "Completed"
    plan.completed_by = actor_id
    plan.completed_at = utcnow()
    plan.outcome_summary = outcome_summary
    return {"task_count": len(tasks), "verification_review_id": str(verification.id)}
