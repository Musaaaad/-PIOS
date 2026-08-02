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
    InstitutionalPilotRun,
    Organization,
    PilotAdoptionEvent,
    PilotDataSourceAttestation,
    PilotFeedbackRecord,
    PilotIdentityBinding,
    PilotOutcomeMetric,
    PilotOutcomeReport,
    PilotSessionExecution,
    Site,
)
from app.schemas.institutional_pilot import (
    AdoptionEventCreate,
    AdoptionEventRead,
    DataSourceAttestationCreate,
    DataSourceAttestationRead,
    FeedbackCreate,
    FeedbackRead,
    IdentityBindingCreate,
    IdentityBindingRead,
    InstitutionalPilotCreate,
    InstitutionalPilotRead,
    LifecycleComment,
    OutcomeMetricCreate,
    OutcomeMetricRead,
    OutcomeReportCreate,
    OutcomeReportRead,
    PilotSessionLink,
    PilotSessionPatch,
    PilotSessionRead,
    ReportPublish,
)
from app.services.institutional_pilot import (
    activate_pilot,
    approve_report,
    attest_data_source,
    bind_identity,
    complete_pilot,
    completion_evaluation,
    create_pilot_run,
    evaluate_activation,
    generate_report,
    link_session,
    publish_report,
    record_adoption,
    record_feedback,
    record_metric,
    refresh_session_execution,
    start_observation,
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


def _run(db: Session, row_id: UUID):
    row = db.get(InstitutionalPilotRun, row_id)
    if not row:
        raise HTTPException(404, "Institutional pilot run not found")
    return row


def _session(db: Session, row_id: UUID):
    row = db.get(PilotSessionExecution, row_id)
    if not row:
        raise HTTPException(404, "Pilot session execution not found")
    return row


def _report(db: Session, row_id: UUID):
    row = db.get(PilotOutcomeReport, row_id)
    if not row:
        raise HTTPException(404, "Pilot outcome report not found")
    return row


@router.post("/institutional-pilot/runs", response_model=InstitutionalPilotRead, status_code=201)
def pilot_run_create(payload: InstitutionalPilotCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))]):
    org, site = _ctx(db)
    row, created = create_pilot_run(db, site.id, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "institutional_pilot.run.create", "InstitutionalPilotRun", str(row.id), after=payload.model_dump(mode="json") | {"created": created})
    db.commit(); db.refresh(row); return row


@router.get("/institutional-pilot/runs")
def pilot_run_list(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _, site = _ctx(db)
    rows = list(db.scalars(select(InstitutionalPilotRun).where(InstitutionalPilotRun.site_id == site.id).order_by(InstitutionalPilotRun.created_at.desc())).all())
    return {"items": [InstitutionalPilotRead.model_validate(x) for x in rows], "total": len(rows)}


@router.get("/institutional-pilot/runs/{run_id}")
def pilot_run_detail(run_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    row = _run(db, run_id)
    identities = list(db.scalars(select(PilotIdentityBinding).where(PilotIdentityBinding.pilot_run_id == row.id)).all())
    sources = list(db.scalars(select(PilotDataSourceAttestation).where(PilotDataSourceAttestation.pilot_run_id == row.id)).all())
    sessions = list(db.scalars(select(PilotSessionExecution).where(PilotSessionExecution.pilot_run_id == row.id).order_by(PilotSessionExecution.sequence)).all())
    metrics = list(db.scalars(select(PilotOutcomeMetric).where(PilotOutcomeMetric.pilot_run_id == row.id).order_by(PilotOutcomeMetric.code)).all())
    reports = list(db.scalars(select(PilotOutcomeReport).where(PilotOutcomeReport.pilot_run_id == row.id).order_by(PilotOutcomeReport.generated_at.desc())).all())
    return {
        "run": InstitutionalPilotRead.model_validate(row),
        "identities": [IdentityBindingRead.model_validate(x) for x in identities],
        "sources": [DataSourceAttestationRead.model_validate(x) for x in sources],
        "sessions": [PilotSessionRead.model_validate(refresh_session_execution(db, x)) for x in sessions],
        "metrics": [OutcomeMetricRead.model_validate(x) for x in metrics],
        "reports": [OutcomeReportRead.model_validate(x) for x in reports],
    }


@router.post("/institutional-pilot/runs/{run_id}/identities", response_model=IdentityBindingRead)
def identity_bind(run_id: UUID, payload: IdentityBindingCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead"))]):
    org, _ = _ctx(db); run = _run(db, run_id)
    row = bind_identity(db, run, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "institutional_pilot.identity.bind", "PilotIdentityBinding", str(row.id), after={k: v for k, v in payload.model_dump(mode="json").items() if k != "external_subject"} | {"subject_hash": row.subject_hash, "verified": row.verified})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-pilot/runs/{run_id}/data-sources", response_model=DataSourceAttestationRead)
def source_attest(run_id: UUID, payload: DataSourceAttestationCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "ReadOnlyAuditor", "MedicationSafety"))]):
    org, _ = _ctx(db); run = _run(db, run_id)
    row = attest_data_source(db, run, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "institutional_pilot.data.attest", "PilotDataSourceAttestation", str(row.id), after=payload.model_dump(mode="json"))
    db.commit(); db.refresh(row); return row


@router.post("/institutional-pilot/runs/{run_id}/evaluate")
def pilot_evaluate(run_id: UUID, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "ReadOnlyAuditor"))]):
    org, _ = _ctx(db); run = _run(db, run_id); evaluation = evaluate_activation(db, run)
    add_audit_event(db, request, principal, org.id, "institutional_pilot.evaluate", "InstitutionalPilotRun", str(run.id), after=evaluation)
    db.commit(); db.refresh(run); return {"run": InstitutionalPilotRead.model_validate(run), "evaluation": evaluation}


@router.post("/institutional-pilot/runs/{run_id}/activate", response_model=InstitutionalPilotRead)
def pilot_activate(run_id: UUID, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("PharmacyDirector", "SystemAdmin"))]):
    org, _ = _ctx(db); run = _run(db, run_id); evaluation = activate_pilot(db, run, _actor(principal))
    add_audit_event(db, request, principal, org.id, "institutional_pilot.activate", "InstitutionalPilotRun", str(run.id), after=evaluation)
    db.commit(); db.refresh(run); return run


@router.post("/institutional-pilot/runs/{run_id}/sessions", response_model=PilotSessionRead, status_code=201)
def pilot_session_link(run_id: UUID, payload: PilotSessionLink, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))]):
    org, _ = _ctx(db); run = _run(db, run_id); row, created = link_session(db, run, payload)
    add_audit_event(db, request, principal, org.id, "institutional_pilot.session.link", "PilotSessionExecution", str(row.id), after=payload.model_dump(mode="json") | {"created": created})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-pilot/session-executions/{execution_id}/refresh", response_model=PilotSessionRead)
def pilot_session_refresh(execution_id: UUID, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "ReadOnlyAuditor"))]):
    org, _ = _ctx(db); row = _session(db, execution_id); refresh_session_execution(db, row)
    add_audit_event(db, request, principal, org.id, "institutional_pilot.session.refresh", "PilotSessionExecution", str(row.id), after=row.summary_json)
    db.commit(); db.refresh(row); return row


@router.post("/institutional-pilot/runs/{run_id}/observation", response_model=InstitutionalPilotRead)
def pilot_observation_start(run_id: UUID, payload: LifecycleComment, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("AccreditationLead", "PharmacyDirector"))]):
    org, _ = _ctx(db); run = _run(db, run_id); start_observation(db, run)
    add_audit_event(db, request, principal, org.id, "institutional_pilot.observation.start", "InstitutionalPilotRun", str(run.id), after={"status": run.status, "comment": payload.comment})
    db.commit(); db.refresh(run); return run


@router.post("/institutional-pilot/runs/{run_id}/metrics", response_model=OutcomeMetricRead)
def outcome_metric_upsert(run_id: UUID, payload: OutcomeMetricCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "ReadOnlyAuditor"))]):
    org, _ = _ctx(db); run = _run(db, run_id); row = record_metric(db, run, payload)
    add_audit_event(db, request, principal, org.id, "institutional_pilot.metric.record", "PilotOutcomeMetric", str(row.id), after=payload.model_dump() | {"status": row.status})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-pilot/runs/{run_id}/adoption-events", response_model=AdoptionEventRead, status_code=201)
def adoption_event_record(run_id: UUID, payload: AdoptionEventCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "MedicationSafety"))]):
    org, _ = _ctx(db); run = _run(db, run_id); row = record_adoption(db, run, payload)
    add_audit_event(db, request, principal, org.id, "institutional_pilot.adoption.record", "PilotAdoptionEvent", str(row.id), after={k: v for k, v in payload.model_dump(mode="json").items() if k != "actor_reference"})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-pilot/runs/{run_id}/feedback", response_model=FeedbackRead, status_code=201)
def feedback_record(run_id: UUID, payload: FeedbackCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "MedicationSafety", "EvidenceCollector", "EvidenceReviewer", "MEOwner"))]):
    org, _ = _ctx(db); run = _run(db, run_id); row = record_feedback(db, run, payload)
    add_audit_event(db, request, principal, org.id, "institutional_pilot.feedback.record", "PilotFeedbackRecord", str(row.id), after={k: v for k, v in payload.model_dump().items() if k != "respondent_reference"} | {"respondent_token": row.respondent_token})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-pilot/runs/{run_id}/complete", response_model=InstitutionalPilotRead)
def pilot_complete(run_id: UUID, payload: LifecycleComment, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("PharmacyDirector", "AccreditationLead"))]):
    org, _ = _ctx(db); run = _run(db, run_id); evaluation = complete_pilot(db, run)
    add_audit_event(db, request, principal, org.id, "institutional_pilot.complete", "InstitutionalPilotRun", str(run.id), after={"evaluation": evaluation, "comment": payload.comment})
    db.commit(); db.refresh(run); return run


@router.get("/institutional-pilot/runs/{run_id}/completion-evaluation")
def pilot_completion_evaluate(run_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    return completion_evaluation(db, _run(db, run_id))


@router.post("/institutional-pilot/runs/{run_id}/reports", response_model=OutcomeReportRead, status_code=201)
def report_generate(run_id: UUID, payload: OutcomeReportCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("AccreditationLead", "PharmacyDirector", "ReadOnlyAuditor"))]):
    org, _ = _ctx(db); run = _run(db, run_id); row, created = generate_report(db, run, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "institutional_pilot.report.generate", "PilotOutcomeReport", str(row.id), after=payload.model_dump() | {"created": created, "summary": row.summary_json})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-pilot/reports/{report_id}/approve", response_model=OutcomeReportRead)
def report_approve(report_id: UUID, payload: LifecycleComment, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("PharmacyDirector", "ReadOnlyAuditor"))]):
    org, _ = _ctx(db); row = _report(db, report_id); approve_report(row, _actor(principal))
    add_audit_event(db, request, principal, org.id, "institutional_pilot.report.approve", "PilotOutcomeReport", str(row.id), after={"status": row.status, "comment": payload.comment})
    db.commit(); db.refresh(row); return row


@router.post("/institutional-pilot/reports/{report_id}/publish", response_model=OutcomeReportRead)
def report_publish(report_id: UUID, payload: ReportPublish, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("PharmacyDirector", "SystemAdmin"))]):
    org, _ = _ctx(db); row = _report(db, report_id); publish_report(row, payload, _actor(principal))
    add_audit_event(db, request, principal, org.id, "institutional_pilot.report.publish", "PilotOutcomeReport", str(row.id), after=payload.model_dump() | {"status": row.status})
    db.commit(); db.refresh(row); return row


@router.get("/institutional-pilot/dashboard")
def pilot_dashboard(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _, site = _ctx(db)
    runs = list(db.scalars(select(InstitutionalPilotRun).where(InstitutionalPilotRun.site_id == site.id)).all())
    run_ids = [x.id for x in runs]
    sessions = list(db.scalars(select(PilotSessionExecution).where(PilotSessionExecution.pilot_run_id.in_(run_ids))).all()) if run_ids else []
    metrics = list(db.scalars(select(PilotOutcomeMetric).where(PilotOutcomeMetric.pilot_run_id.in_(run_ids))).all()) if run_ids else []
    feedback = list(db.scalars(select(PilotFeedbackRecord).where(PilotFeedbackRecord.pilot_run_id.in_(run_ids))).all()) if run_ids else []
    reports = list(db.scalars(select(PilotOutcomeReport).where(PilotOutcomeReport.pilot_run_id.in_(run_ids))).all()) if run_ids else []
    identities = int(db.scalar(select(func.count(PilotIdentityBinding.id)).where(PilotIdentityBinding.pilot_run_id.in_(run_ids), PilotIdentityBinding.verified.is_(True))) or 0) if run_ids else 0
    adoption = int(db.scalar(select(func.sum(PilotAdoptionEvent.event_count)).where(PilotAdoptionEvent.pilot_run_id.in_(run_ids))) or 0) if run_ids else 0
    return {
        "site_code": site.code,
        "runs_total": len(runs),
        "institutional_runs": sum(x.run_mode == "Institutional" for x in runs),
        "active_runs": sum(x.status in {"Active", "Observation"} for x in runs),
        "completed_runs": sum(x.status == "Completed" for x in runs),
        "verified_identities": identities,
        "linked_sessions": len(sessions),
        "completed_sessions": sum(x.status == "Completed" for x in sessions),
        "measured_metrics": sum(x.status != "NotMeasured" for x in metrics),
        "target_met_metrics": sum(x.status == "TargetMet" for x in metrics),
        "adoption_events": adoption,
        "feedback_count": len(feedback),
        "average_feedback": round(sum(x.rating for x in feedback) / len(feedback), 2) if feedback else None,
        "published_reports": sum(x.status == "Published" for x in reports),
        "guardrail": "Institutional pilot dashboards report controlled execution and outcomes; they do not approve CBAHI compliance or accreditation readiness.",
    }
