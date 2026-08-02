from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from statistics import median
from typing import Iterable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AiRecommendation,
    CommitteeConflictDeclaration,
    CommitteeMembership,
    CommitteeSessionAttendance,
    DecisionMetricsSnapshot,
    DecisionQualityReview,
    DecisionSlaPolicy,
    InstitutionalCommittee,
    IntelligenceActionPlan,
    IntelligenceReviewItem,
    IntelligenceReviewSession,
    SessionGovernance,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_committee(db: Session, site_id: UUID, payload, actor_id=None):
    existing = db.scalar(select(InstitutionalCommittee).where(InstitutionalCommittee.site_id == site_id, InstitutionalCommittee.code == payload.code))
    if existing:
        return existing, False
    row = InstitutionalCommittee(site_id=site_id, created_by=actor_id, **payload.model_dump())
    db.add(row); db.flush()
    return row, True


def activate_committee(db: Session, committee: InstitutionalCommittee, actor_id=None):
    if committee.status not in {"Draft", "Paused"}:
        raise HTTPException(409, "Only Draft or Paused committees can be activated")
    qualified = db.scalar(select(func.count(CommitteeMembership.id)).where(
        CommitteeMembership.committee_id == committee.id,
        CommitteeMembership.active.is_(True),
        CommitteeMembership.voting_member.is_(True),
        CommitteeMembership.authority_verified.is_(True),
        CommitteeMembership.training_verified.is_(True),
    )) or 0
    chair = db.scalar(select(func.count(CommitteeMembership.id)).where(
        CommitteeMembership.committee_id == committee.id,
        CommitteeMembership.active.is_(True),
        CommitteeMembership.chair.is_(True),
        CommitteeMembership.authority_verified.is_(True),
        CommitteeMembership.training_verified.is_(True),
    )) or 0
    if qualified < committee.quorum_required:
        raise HTTPException(409, f"At least {committee.quorum_required} qualified voting members are required")
    if not chair:
        raise HTTPException(409, "A qualified active chair is required")
    committee.status = "Active"
    committee.activated_by = actor_id
    committee.activated_at = utcnow()
    return {"qualified_voting_members": qualified, "chair_count": chair}


def add_membership(db: Session, committee: InstitutionalCommittee, payload):
    existing = db.scalar(select(CommitteeMembership).where(
        CommitteeMembership.committee_id == committee.id,
        CommitteeMembership.member_code == payload.member_code,
    ))
    if existing:
        return existing, False
    row = CommitteeMembership(committee_id=committee.id, **payload.model_dump())
    db.add(row); db.flush()
    return row, True


def patch_membership(row: CommitteeMembership, payload):
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, name, value)
    return row


def bind_session(db: Session, session: IntelligenceReviewSession, committee: InstitutionalCommittee):
    if session.site_id != committee.site_id:
        raise HTTPException(409, "Committee and review session must belong to the same site")
    existing = db.scalar(select(SessionGovernance).where(SessionGovernance.review_session_id == session.id))
    if existing:
        if existing.committee_id != committee.id:
            raise HTTPException(409, "Review session is already bound to another committee")
        return existing, False
    row = SessionGovernance(review_session_id=session.id, committee_id=committee.id)
    db.add(row); db.flush()
    return row, True


def upsert_attendance(db: Session, governance: SessionGovernance, payload, actor_id=None):
    member = db.get(CommitteeMembership, payload.membership_id)
    if not member or member.committee_id != governance.committee_id:
        raise HTTPException(404, "Committee membership not found for this session")
    row = db.scalar(select(CommitteeSessionAttendance).where(
        CommitteeSessionAttendance.governance_id == governance.id,
        CommitteeSessionAttendance.membership_id == member.id,
    ))
    values = payload.model_dump(exclude={"membership_id"})
    if not row:
        row = CommitteeSessionAttendance(governance_id=governance.id, membership_id=member.id)
        db.add(row)
    for name, value in values.items():
        setattr(row, name, value)
    row.recorded_by = actor_id
    row.recorded_at = utcnow()
    db.flush()
    return row


def declare_conflict(db: Session, governance: SessionGovernance, payload, actor_id=None):
    item = db.get(IntelligenceReviewItem, payload.review_item_id)
    member = db.get(CommitteeMembership, payload.membership_id)
    if not item or item.session_id != governance.review_session_id:
        raise HTTPException(404, "Review item not found in this governed session")
    if not member or member.committee_id != governance.committee_id:
        raise HTTPException(404, "Committee membership not found")
    row = db.scalar(select(CommitteeConflictDeclaration).where(
        CommitteeConflictDeclaration.review_item_id == item.id,
        CommitteeConflictDeclaration.membership_id == member.id,
    ))
    values = payload.model_dump(exclude={"review_item_id", "membership_id"})
    if not row:
        row = CommitteeConflictDeclaration(
            governance_id=governance.id,
            review_item_id=item.id,
            membership_id=member.id,
            declared_by=actor_id,
        )
        db.add(row)
    for name, value in values.items():
        setattr(row, name, value)
    row.status = "Resolved" if (not row.has_conflict or row.disposition in {"Recused", "Managed"}) else "Declared"
    if row.status == "Resolved":
        row.resolved_at = utcnow()
        row.resolved_by = actor_id
    db.flush()
    return row


def resolve_conflict(row: CommitteeConflictDeclaration, payload, actor_id=None):
    if not row.has_conflict:
        raise HTTPException(409, "No conflict requires resolution")
    row.disposition = payload.disposition
    row.status = "Resolved"
    row.resolved_by = actor_id
    row.resolved_at = utcnow()
    row.evidence_reference = payload.evidence_reference or row.evidence_reference
    row.description = f"{row.description or ''}\nResolution: {payload.comment}".strip()
    return row


def evaluate_governance(db: Session, governance: SessionGovernance, actor_id=None):
    committee = db.get(InstitutionalCommittee, governance.committee_id)
    if not committee:
        raise HTTPException(404, "Committee not found")
    members = list(db.scalars(select(CommitteeMembership).where(
        CommitteeMembership.committee_id == committee.id,
        CommitteeMembership.active.is_(True),
        CommitteeMembership.voting_member.is_(True),
    )).all())
    qualified_ids = {
        m.id for m in members if m.authority_verified and m.training_verified and
        (m.term_end is None or m.term_end >= utcnow().date())
    }
    attendance = list(db.scalars(select(CommitteeSessionAttendance).where(
        CommitteeSessionAttendance.governance_id == governance.id,
    )).all())
    attended = [a for a in attendance if a.attended and a.voting_eligible and not a.recused and a.membership_id in qualified_ids]
    items = list(db.scalars(select(IntelligenceReviewItem).where(IntelligenceReviewItem.session_id == governance.review_session_id)).all())
    required_pairs = {(item.id, a.membership_id) for item in items for a in attended}
    declarations = list(db.scalars(select(CommitteeConflictDeclaration).where(
        CommitteeConflictDeclaration.governance_id == governance.id,
    )).all())
    declared_pairs = {(x.review_item_id, x.membership_id) for x in declarations}
    unresolved = [x for x in declarations if x.has_conflict and (x.status != "Resolved" or x.disposition not in {"Recused", "Managed"})]
    conflicts_complete = bool(items) and required_pairs.issubset(declared_pairs)
    authorized_roles = sorted({m.role_code for m in members for a in attended if a.membership_id == m.id})
    governance.expected_voting_members = len(qualified_ids)
    governance.attended_voting_members = len(attended)
    governance.quorum_met = len(attended) >= committee.quorum_required
    governance.conflicts_complete = conflicts_complete
    governance.unresolved_conflicts = len(unresolved)
    governance.authorized_roles = authorized_roles
    ready = committee.status == "Active" and governance.quorum_met and conflicts_complete and not unresolved and bool(items)
    governance.status = "Ready" if ready else "Blocked"
    governance.evaluation_json = {
        "committee_status": committee.status,
        "qualified_voting_members": len(qualified_ids),
        "attended_voting_members": len(attended),
        "quorum_required": committee.quorum_required,
        "review_items": len(items),
        "declarations_required": len(required_pairs),
        "declarations_recorded": len(required_pairs & declared_pairs),
        "unresolved_conflicts": len(unresolved),
        "authorized_roles": authorized_roles,
        "ready": ready,
    }
    governance.evaluated_by = actor_id
    governance.evaluated_at = utcnow()
    return governance.evaluation_json


def governance_for_session(db: Session, session_id: UUID):
    return db.scalar(select(SessionGovernance).where(SessionGovernance.review_session_id == session_id))


def ensure_session_governance_ready(db: Session, session_id: UUID, actor_roles: Iterable[str] | None = None, require_actor=False):
    governance = governance_for_session(db, session_id)
    if not governance:
        return None
    evaluation = evaluate_governance(db, governance)
    if not evaluation["ready"]:
        raise HTTPException(409, "Committee governance, quorum and conflict declarations are not ready")
    if require_actor and actor_roles is not None and not set(actor_roles).intersection(governance.authorized_roles):
        raise HTTPException(403, "Actor is not an attended and authorized committee role")
    return governance


def create_sla_policy(db: Session, site_id: UUID, payload, actor_id=None):
    existing = db.scalar(select(DecisionSlaPolicy).where(DecisionSlaPolicy.site_id == site_id, DecisionSlaPolicy.code == payload.code))
    if existing:
        return existing, False
    for current in db.scalars(select(DecisionSlaPolicy).where(DecisionSlaPolicy.site_id == site_id, DecisionSlaPolicy.active.is_(True))).all():
        current.active = False
    row = DecisionSlaPolicy(site_id=site_id, approved_by=actor_id, approved_at=utcnow(), **payload.model_dump())
    db.add(row); db.flush()
    return row, True


def add_quality_review(db: Session, item: IntelligenceReviewItem, payload, actor_id=None):
    if item.status != "DecisionRecorded" or not item.decision:
        raise HTTPException(409, "A recorded committee decision is required")
    existing = db.scalar(select(DecisionQualityReview).where(
        DecisionQualityReview.review_item_id == item.id,
        DecisionQualityReview.review_type == payload.review_type,
    ))
    if existing:
        raise HTTPException(409, "This decision quality review already exists")
    scores = [payload.rationale_score, payload.evidence_score, payload.policy_alignment_score, payload.conflict_management_score, payload.bias_check_score]
    quality_score = round(sum(scores) / 25 * 100, 1)
    outcome = "Pass" if quality_score >= 80 else "NeedsImprovement" if quality_score >= 60 else "Fail"
    row = DecisionQualityReview(
        review_item_id=item.id,
        review_type=payload.review_type,
        rationale_score=payload.rationale_score,
        evidence_score=payload.evidence_score,
        policy_alignment_score=payload.policy_alignment_score,
        conflict_management_score=payload.conflict_management_score,
        bias_check_score=payload.bias_check_score,
        quality_score=quality_score,
        outcome=outcome,
        comment=payload.comment,
        reviewer_role_code=payload.reviewer_role_code,
        reviewed_by=actor_id,
        reviewed_at=utcnow(),
    )
    db.add(row); db.flush()
    return row


def _p90(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, ceil(len(ordered) * 0.9) - 1)]


def generate_metrics_snapshot(db: Session, site_id: UUID, payload, actor_id=None):
    existing = db.scalar(select(DecisionMetricsSnapshot).where(DecisionMetricsSnapshot.site_id == site_id, DecisionMetricsSnapshot.code == payload.code))
    if existing:
        return existing, False
    sessions = list(db.scalars(select(IntelligenceReviewSession).where(
        IntelligenceReviewSession.site_id == site_id,
        IntelligenceReviewSession.scheduled_at >= payload.period_start,
        IntelligenceReviewSession.scheduled_at <= payload.period_end,
    )).all())
    session_ids = [x.id for x in sessions]
    items = [] if not session_ids else list(db.scalars(select(IntelligenceReviewItem).where(IntelligenceReviewItem.session_id.in_(session_ids))).all())
    decided = [x for x in items if x.status == "DecisionRecorded" and x.decided_at]
    recommendation_ids = [x.recommendation_id for x in decided]
    recommendations = {x.id: x for x in db.scalars(select(AiRecommendation).where(AiRecommendation.id.in_(recommendation_ids))).all()} if recommendation_ids else {}
    decision_hours = []
    for item in decided:
        recommendation = recommendations.get(item.recommendation_id)
        if recommendation and recommendation.created_at and item.decided_at:
            decision_hours.append(max(0.0, (item.decided_at - recommendation.created_at).total_seconds() / 3600))
    plans = list(db.scalars(select(IntelligenceActionPlan).where(IntelligenceActionPlan.site_id == site_id, IntelligenceActionPlan.recommendation_id.in_(recommendation_ids))).all()) if recommendation_ids else []
    decided_at_by_rec = {x.recommendation_id: x.decided_at for x in decided}
    plan_days = []
    for plan in plans:
        decided_at = decided_at_by_rec.get(plan.recommendation_id)
        if decided_at and plan.created_at:
            plan_days.append(max(0.0, (plan.created_at - decided_at).total_seconds() / 86400))
    quality_rows = list(db.scalars(select(DecisionQualityReview).join(IntelligenceReviewItem, IntelligenceReviewItem.id == DecisionQualityReview.review_item_id).where(IntelligenceReviewItem.session_id.in_(session_ids))).all()) if session_ids else []
    unresolved_conflicts = db.scalar(select(func.count(CommitteeConflictDeclaration.id)).join(SessionGovernance, SessionGovernance.id == CommitteeConflictDeclaration.governance_id).where(
        SessionGovernance.review_session_id.in_(session_ids),
        CommitteeConflictDeclaration.has_conflict.is_(True),
        CommitteeConflictDeclaration.status != "Resolved",
    )) if session_ids else 0
    policy = db.scalar(select(DecisionSlaPolicy).where(DecisionSlaPolicy.site_id == site_id, DecisionSlaPolicy.active.is_(True)).order_by(DecisionSlaPolicy.created_at.desc()).limit(1))
    total_decision_target = (policy.recommendation_to_review_hours + policy.review_to_decision_hours) if policy else 96
    plan_target = policy.decision_to_plan_days if policy else 7
    breaches = sum(v > total_decision_target for v in decision_hours) + sum(v > plan_target for v in plan_days)
    row = DecisionMetricsSnapshot(
        site_id=site_id,
        code=payload.code,
        period_start=payload.period_start,
        period_end=payload.period_end,
        session_count=len(sessions),
        decision_count=len(decided),
        adopted_count=sum(x.decision == "AdoptForPlanning" for x in decided),
        action_plan_count=len(plans),
        median_decision_hours=round(median(decision_hours), 2) if decision_hours else None,
        p90_decision_hours=round(_p90(decision_hours), 2) if decision_hours else None,
        median_plan_days=round(median(plan_days), 2) if plan_days else None,
        sla_breach_count=breaches,
        average_quality_score=round(sum(x.quality_score for x in quality_rows) / len(quality_rows), 1) if quality_rows else None,
        unresolved_conflict_count=int(unresolved_conflicts or 0),
        summary_json={
            "decision_hours": [round(x, 2) for x in decision_hours],
            "plan_days": [round(x, 2) for x in plan_days],
            "policy_code": policy.code if policy else None,
            "guardrail": "Metrics measure governance timeliness and documentation quality; they do not score accreditation compliance.",
        },
        generated_by=actor_id,
        generated_at=utcnow(),
    )
    db.add(row); db.flush()
    return row, True
