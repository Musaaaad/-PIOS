from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    CommitteeMembership,
    DecisionQualityReview,
    InstitutionalCommittee,
    InstitutionalPilotRun,
    IntelligenceReviewItem,
    IntelligenceReviewSession,
    OperationalIncident,
    PilotAdoptionEvent,
    PilotDataSourceAttestation,
    PilotDecision,
    PilotFeedbackRecord,
    PilotIdentityBinding,
    PilotOutcomeMetric,
    PilotOutcomeReport,
    PilotSessionExecution,
    SessionGovernance,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


def create_pilot_run(db: Session, site_id: UUID, payload, actor_id=None):
    existing = db.scalar(select(InstitutionalPilotRun).where(
        InstitutionalPilotRun.site_id == site_id,
        InstitutionalPilotRun.code == payload.code,
    ))
    if existing:
        return existing, False
    if payload.committee_id:
        committee = db.get(InstitutionalCommittee, payload.committee_id)
        if not committee or committee.site_id != site_id:
            raise ValueError("Committee does not belong to the pilot site")
    row = InstitutionalPilotRun(
        site_id=site_id,
        pilot_cycle_id=payload.pilot_cycle_id,
        committee_id=payload.committee_id,
        code=payload.code,
        title=payload.title,
        objective=payload.objective,
        run_mode=payload.run_mode,
        status="Draft",
        period_start=payload.period_start,
        period_end=payload.period_end,
        environment_reference=payload.environment_reference,
        oidc_required=payload.oidc_required,
        institutional_data_required=payload.institutional_data_required,
        summary_json={
            "created_by": str(actor_id) if actor_id else None,
            "guardrail": "Synthetic or local pilot results are not institutional evidence or accreditation readiness.",
        },
    )
    db.add(row); db.flush()
    return row, True


def bind_identity(db: Session, run: InstitutionalPilotRun, payload, actor_id=None):
    if run.status in {"Completed", "RolledBack"}:
        raise ValueError("Cannot modify identities after pilot closure")
    if run.run_mode == "Institutional" and not payload.issuer.startswith("https://"):
        raise ValueError("Institutional pilot identity issuer must use HTTPS")
    subject_hash = token_hash(payload.external_subject)
    row = db.scalar(select(PilotIdentityBinding).where(
        PilotIdentityBinding.pilot_run_id == run.id,
        PilotIdentityBinding.subject_hash == subject_hash,
    ))
    if not row:
        row = PilotIdentityBinding(pilot_run_id=run.id, subject_hash=subject_hash, issuer=payload.issuer)
        db.add(row)
    if payload.membership_id:
        membership = db.get(CommitteeMembership, payload.membership_id)
        if not membership or (run.committee_id and membership.committee_id != run.committee_id):
            raise ValueError("Committee membership is not valid for this pilot")
        row.membership_id = membership.id
        row.user_id = membership.user_id
    row.issuer = payload.issuer
    row.email_hint = payload.email_hint
    row.role_codes = sorted(set(payload.role_codes))
    row.site_codes = sorted(set(payload.site_codes))
    row.authority_verified = payload.authority_verified
    row.training_verified = payload.training_verified
    row.site_scope_verified = payload.site_scope_verified and bool(row.site_codes)
    row.evidence_reference = payload.evidence_reference
    row.verified = bool(
        row.authority_verified and row.training_verified and row.site_scope_verified
        and row.role_codes and row.site_codes and row.evidence_reference
    )
    row.verified_at = utcnow() if row.verified else None
    row.active = True
    db.flush()
    return row


def attest_data_source(db: Session, run: InstitutionalPilotRun, payload, actor_id=None):
    if run.status in {"Completed", "RolledBack"}:
        raise ValueError("Cannot attest data after pilot closure")
    if payload.data_classification != run.run_mode:
        raise ValueError("Data classification must match the pilot run mode")
    if run.run_mode == "Institutional" and payload.record_count <= 0:
        raise ValueError("Institutional source attestation requires a positive record count")
    row = db.scalar(select(PilotDataSourceAttestation).where(
        PilotDataSourceAttestation.pilot_run_id == run.id,
        PilotDataSourceAttestation.code == payload.code,
    ))
    if not row:
        row = PilotDataSourceAttestation(pilot_run_id=run.id, code=payload.code)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.attested_by = actor_id
    row.attested_at = utcnow() if row.attested else None
    db.flush()
    return row


def _latest_pilot_decision(db: Session, run: InstitutionalPilotRun):
    if not run.pilot_cycle_id:
        return None
    return db.scalar(select(PilotDecision).where(PilotDecision.pilot_cycle_id == run.pilot_cycle_id).order_by(PilotDecision.decided_at.desc()).limit(1))


def evaluate_activation(db: Session, run: InstitutionalPilotRun):
    committee = db.get(InstitutionalCommittee, run.committee_id) if run.committee_id else None
    quorum = committee.quorum_required if committee else 3
    verified_identities = int(db.scalar(select(func.count(PilotIdentityBinding.id)).where(
        PilotIdentityBinding.pilot_run_id == run.id,
        PilotIdentityBinding.active.is_(True),
        PilotIdentityBinding.verified.is_(True),
    )) or 0)
    classifications = list(db.scalars(select(PilotDataSourceAttestation.data_classification).where(
        PilotDataSourceAttestation.pilot_run_id == run.id,
        PilotDataSourceAttestation.attested.is_(True),
        PilotDataSourceAttestation.contains_patient_identifiers.is_(False),
        PilotDataSourceAttestation.deidentified_or_tokenized.is_(True),
    )).all())
    open_critical_incidents = int(db.scalar(select(func.count(OperationalIncident.id)).where(
        OperationalIncident.site_id == run.site_id,
        OperationalIncident.severity.in_(["P0", "P1"]),
        OperationalIncident.status != "Closed",
    )) or 0)
    decision = _latest_pilot_decision(db, run)
    pilot_decision_ok = not run.pilot_cycle_id or bool(decision and decision.decision in {"Go", "ConditionalGo"})
    committee_ok = bool(committee and committee.status == "Active")
    identity_ok = (not run.oidc_required) or verified_identities >= quorum
    data_ok = (not run.institutional_data_required) or run.run_mode in classifications
    ready = committee_ok and identity_ok and data_ok and open_critical_incidents == 0 and pilot_decision_ok
    evaluation = {
        "ready": ready,
        "run_mode": run.run_mode,
        "committee_active": committee_ok,
        "quorum_required": quorum,
        "verified_identities": verified_identities,
        "identity_gate": identity_ok,
        "attested_classifications": sorted(set(classifications)),
        "data_gate": data_ok,
        "open_p0_p1_incidents": open_critical_incidents,
        "pilot_decision": decision.decision if decision else None,
        "pilot_decision_gate": pilot_decision_ok,
        "institutional_claim_allowed": bool(ready and run.run_mode == "Institutional"),
        "guardrail": "Readiness here authorizes a controlled pilot only; it does not approve accreditation compliance.",
    }
    run.summary_json = evaluation
    if run.status in {"Draft", "Ready"}:
        run.status = "Ready" if ready else "Draft"
    db.flush()
    return evaluation


def activate_pilot(db: Session, run: InstitutionalPilotRun, actor_id=None):
    evaluation = evaluate_activation(db, run)
    if not evaluation["ready"]:
        raise ValueError("Institutional pilot activation gates are not complete")
    run.status = "Active"
    run.activated_at = utcnow()
    run.approved_by = actor_id
    db.flush()
    return evaluation


def link_session(db: Session, run: InstitutionalPilotRun, payload):
    if run.status not in {"Active", "Observation"}:
        raise ValueError("Pilot must be Active or Observation before linking a live session")
    session = db.get(IntelligenceReviewSession, payload.review_session_id)
    if not session or session.site_id != run.site_id:
        raise ValueError("Review session does not belong to the pilot site")
    governance = db.scalar(select(SessionGovernance).where(SessionGovernance.review_session_id == session.id))
    if not governance:
        raise ValueError("Review session must be bound to institutional governance")
    existing = db.scalar(select(PilotSessionExecution).where(
        PilotSessionExecution.pilot_run_id == run.id,
        PilotSessionExecution.review_session_id == session.id,
    ))
    if existing:
        return existing, False
    row = PilotSessionExecution(
        pilot_run_id=run.id,
        review_session_id=session.id,
        governance_id=governance.id,
        sequence=payload.sequence,
        status="Planned",
        live_data_attested=payload.live_data_attested,
        governance_ready=governance.status == "Ready",
        evidence_reference=payload.evidence_reference,
        summary_json={},
    )
    db.add(row); db.flush()
    return row, True


def refresh_session_execution(db: Session, row: PilotSessionExecution):
    session = db.get(IntelligenceReviewSession, row.review_session_id)
    governance = db.get(SessionGovernance, row.governance_id) if row.governance_id else None
    item_ids = list(db.scalars(select(IntelligenceReviewItem.id).where(IntelligenceReviewItem.session_id == row.review_session_id)).all())
    decisions = int(db.scalar(select(func.count(IntelligenceReviewItem.id)).where(
        IntelligenceReviewItem.session_id == row.review_session_id,
        IntelligenceReviewItem.status == "DecisionRecorded",
    )) or 0)
    quality = int(db.scalar(select(func.count(DecisionQualityReview.id)).where(
        DecisionQualityReview.review_item_id.in_(item_ids),
    )) or 0) if item_ids else 0
    row.governance_ready = bool(governance and governance.status == "Ready")
    row.decision_count = decisions
    row.quality_review_count = quality
    if session and session.status == "Open" and not row.started_at:
        row.status = "Active"
        row.started_at = session.opened_at or utcnow()
    if session and session.status == "Closed":
        row.status = "Completed"
        row.completed_at = session.closed_at or utcnow()
    row.summary_json = {
        "session_status": session.status if session else None,
        "governance_status": governance.status if governance else None,
        "decisions": decisions,
        "quality_reviews": quality,
        "quality_complete": decisions > 0 and quality >= decisions,
    }
    db.flush()
    return row


def record_metric(db: Session, run: InstitutionalPilotRun, payload):
    row = db.scalar(select(PilotOutcomeMetric).where(
        PilotOutcomeMetric.pilot_run_id == run.id,
        PilotOutcomeMetric.code == payload.code,
    ))
    if not row:
        row = PilotOutcomeMetric(pilot_run_id=run.id, code=payload.code)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    if row.current_value is None or row.target_value is None:
        row.status = "NotMeasured"
        row.measured_at = None
    else:
        if row.direction == "HigherIsBetter":
            met = row.current_value >= row.target_value
        elif row.direction == "LowerIsBetter":
            met = row.current_value <= row.target_value
        else:
            met = abs(row.current_value - row.target_value) <= max(abs(row.target_value) * 0.05, 0.01)
        row.status = "TargetMet" if met else "BelowTarget"
        row.measured_at = utcnow()
    db.flush()
    return row


def record_adoption(db: Session, run: InstitutionalPilotRun, payload):
    row = PilotAdoptionEvent(
        pilot_run_id=run.id,
        event_type=payload.event_type,
        role_code=payload.role_code,
        actor_token=token_hash(payload.actor_reference) if payload.actor_reference else None,
        event_count=payload.event_count,
        occurred_at=payload.occurred_at or utcnow(),
        evidence_reference=payload.evidence_reference,
        metadata_json=payload.metadata_json,
    )
    db.add(row); db.flush(); return row


def record_feedback(db: Session, run: InstitutionalPilotRun, payload):
    row = PilotFeedbackRecord(
        pilot_run_id=run.id,
        respondent_token=token_hash(payload.respondent_reference),
        role_code=payload.role_code,
        category=payload.category,
        rating=payload.rating,
        comment=payload.comment,
        contains_patient_data=False,
        status="Recorded",
        recorded_at=utcnow(),
    )
    db.add(row); db.flush(); return row


def completion_evaluation(db: Session, run: InstitutionalPilotRun):
    sessions = list(db.scalars(select(PilotSessionExecution).where(PilotSessionExecution.pilot_run_id == run.id)).all())
    for row in sessions:
        refresh_session_execution(db, row)
    completed_sessions = [x for x in sessions if x.status == "Completed"]
    decisions = sum(x.decision_count for x in completed_sessions)
    quality_reviews = sum(x.quality_review_count for x in completed_sessions)
    metrics = list(db.scalars(select(PilotOutcomeMetric).where(PilotOutcomeMetric.pilot_run_id == run.id)).all())
    measured = [x for x in metrics if x.status != "NotMeasured"]
    open_critical_incidents = int(db.scalar(select(func.count(OperationalIncident.id)).where(
        OperationalIncident.site_id == run.site_id,
        OperationalIncident.severity.in_(["P0", "P1"]),
        OperationalIncident.status != "Closed",
    )) or 0)
    ready = bool(completed_sessions and decisions > 0 and quality_reviews >= decisions and measured and open_critical_incidents == 0)
    return {
        "ready": ready,
        "completed_sessions": len(completed_sessions),
        "decision_count": decisions,
        "quality_review_count": quality_reviews,
        "quality_complete": decisions > 0 and quality_reviews >= decisions,
        "measured_metrics": len(measured),
        "target_met_metrics": sum(x.status == "TargetMet" for x in measured),
        "open_p0_p1_incidents": open_critical_incidents,
        "guardrail": "Outcome completion does not close Findings/CAPAs or approve compliance.",
    }


def start_observation(db: Session, run: InstitutionalPilotRun):
    if run.status != "Active":
        raise ValueError("Pilot must be Active before observation")
    run.status = "Observation"
    run.observation_started_at = utcnow()
    db.flush()


def complete_pilot(db: Session, run: InstitutionalPilotRun):
    evaluation = completion_evaluation(db, run)
    if not evaluation["ready"]:
        raise ValueError("Pilot completion gates are not complete")
    run.status = "Completed"
    run.completed_at = utcnow()
    run.summary_json = {**run.summary_json, "completion": evaluation}
    db.flush()
    return evaluation


def generate_report(db: Session, run: InstitutionalPilotRun, payload, actor_id=None):
    existing = db.scalar(select(PilotOutcomeReport).where(
        PilotOutcomeReport.pilot_run_id == run.id,
        PilotOutcomeReport.code == payload.code,
    ))
    if existing:
        return existing, False
    evaluation = completion_evaluation(db, run)
    if not evaluation["ready"]:
        raise ValueError("Outcome report requires completed governed sessions, quality reviews and measured metrics")
    metrics = list(db.scalars(select(PilotOutcomeMetric).where(PilotOutcomeMetric.pilot_run_id == run.id)).all())
    adoption_count = int(db.scalar(select(func.sum(PilotAdoptionEvent.event_count)).where(PilotAdoptionEvent.pilot_run_id == run.id)) or 0)
    feedback = list(db.scalars(select(PilotFeedbackRecord).where(PilotFeedbackRecord.pilot_run_id == run.id)).all())
    summary = {
        "run_code": run.code,
        "run_mode": run.run_mode,
        "completion": evaluation,
        "metrics": [{"code": x.code, "status": x.status, "current": x.current_value, "target": x.target_value, "unit": x.unit} for x in metrics],
        "adoption_events": adoption_count,
        "feedback_count": len(feedback),
        "average_feedback": round(sum(x.rating for x in feedback) / len(feedback), 2) if feedback else None,
        "institutional_claim_allowed": run.run_mode == "Institutional",
        "guardrail": "The report describes pilot operations and governance outcomes only; it is not an accreditation compliance decision.",
    }
    row = PilotOutcomeReport(
        pilot_run_id=run.id,
        code=payload.code,
        status="Draft",
        data_classification=run.run_mode,
        summary_json=summary,
        conclusions=payload.conclusions,
        limitations=payload.limitations,
        generated_by=actor_id,
        generated_at=utcnow(),
    )
    db.add(row); db.flush(); return row, True


def approve_report(row: PilotOutcomeReport, actor_id=None):
    if row.status != "Draft":
        raise ValueError("Only a Draft pilot report can be approved")
    row.status = "Approved"
    row.approved_by = actor_id
    row.approved_at = utcnow()


def publish_report(row: PilotOutcomeReport, payload, actor_id=None):
    if row.status != "Approved":
        raise ValueError("Pilot report must be Approved before publication")
    row.file_uri = payload.file_uri
    row.sha256 = payload.sha256.lower()
    row.status = "Published"
    row.published_by = actor_id
    row.published_at = utcnow()
