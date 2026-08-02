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
from app.models.entities import (
    Organization, Site, DeploymentEnvironment, PilotCycle, ReadinessSnapshot,
    ServiceLevelObjective, ServiceLevelMeasurement, OperationalIncident,
    IncidentTimelineEntry, CutoverRun, CutoverTask, BaselineRelease,
)
from app.schemas.operations import (
    SloRead, SloMeasurementCreate, SloMeasurementRead, IncidentCreate,
    IncidentTransition, TimelineCreate, IncidentRead, TimelineRead,
    CutoverCreate, CutoverTaskUpdate, CutoverDecision, CutoverRead,
    CutoverTaskRead, BaselineCreate, BaselineRead,
)
from app.services.operations_control import (
    ensure_default_slos, record_measurement, add_timeline, transition_incident,
    ensure_cutover_tasks, evaluate_cutover, decide_cutover, create_baseline,
    publish_baseline,
)

router = APIRouter()


def _actor(principal: Principal):
    try: return UUID(principal.user_id)
    except (ValueError, TypeError): return None


def _org_site(db: Session):
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.code == settings.organization_code))
    if not org: raise HTTPException(409, "Baseline organization is not seeded")
    site = db.scalar(select(Site).where(Site.organization_id == org.id, Site.code == settings.default_site_code))
    if not site: raise HTTPException(404, "Site not found")
    return org, site


def _incident(db: Session, incident_id: UUID):
    row = db.get(OperationalIncident, incident_id)
    if not row: raise HTTPException(404, "Operational incident not found")
    return row


def _cutover(db: Session, run_id: UUID):
    row = db.get(CutoverRun, run_id)
    if not row: raise HTTPException(404, "Cutover run not found")
    return row


@router.post('/operations/slos/bootstrap')
def bootstrap_slos(request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles('SystemAdmin'))]):
    org, site = _org_site(db); created = ensure_default_slos(db, site.id)
    add_audit_event(db, request, principal, org.id, 'operations.slo.bootstrap', 'Site', str(site.id), after={'created': created})
    db.commit(); return {'created': created, 'total': db.scalar(select(func.count(ServiceLevelObjective.id)).where(ServiceLevelObjective.site_id == site.id))}


@router.get('/operations/slos', response_model=list[SloRead])
def list_slos(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _, site = _org_site(db); ensure_default_slos(db, site.id); db.commit()
    return list(db.scalars(select(ServiceLevelObjective).where(ServiceLevelObjective.site_id == site.id, ServiceLevelObjective.active.is_(True)).order_by(ServiceLevelObjective.code)).all())


@router.post('/operations/slos/{objective_id}/measurements', response_model=SloMeasurementRead, status_code=201)
def create_measurement(objective_id: UUID, payload: SloMeasurementCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles('SystemAdmin','ReadOnlyAuditor'))]):
    org, _ = _org_site(db); objective = db.get(ServiceLevelObjective, objective_id)
    if not objective: raise HTTPException(404, 'SLO not found')
    row = record_measurement(db, objective, payload)
    if row.status == 'Breach':
        code = f"SLO-{objective.code}-{payload.window_end.strftime('%Y%m%d%H%M')}"
        existing = db.scalar(select(OperationalIncident).where(OperationalIncident.site_id == objective.site_id, OperationalIncident.code == code))
        if not existing:
            incident = OperationalIncident(site_id=objective.site_id, code=code, title=f"SLO breach: {objective.name}", description=f"Measured {payload.measured_value} {objective.unit}; target {objective.target_operator} {objective.target_value} {objective.unit}", severity=objective.severity_on_breach, category='SLO', source_type='ServiceLevelObjective', source_id=str(objective.id), owner_role_code=objective.owner_role_code, impact_summary='Automated operational threshold breach', created_by=_actor(principal))
            db.add(incident); db.flush(); add_timeline(db, incident, 'Created', incident.description, _actor(principal), status_to='Open', evidence_reference=payload.evidence_reference)
    add_audit_event(db, request, principal, org.id, 'operations.slo.measurement', 'ServiceLevelMeasurement', str(row.id), after=payload.model_dump(mode='json'))
    db.commit(); db.refresh(row); return row


@router.post('/operations/incidents', response_model=IncidentRead, status_code=201)
def create_incident(payload: IncidentCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles('SystemAdmin','PharmacyDirector','AccreditationLead','MedicationSafety'))]):
    org, site = _org_site(db); existing = db.scalar(select(OperationalIncident).where(OperationalIncident.site_id == site.id, OperationalIncident.code == payload.code))
    if existing: return existing
    row = OperationalIncident(site_id=site.id, created_by=_actor(principal), **payload.model_dump())
    db.add(row); db.flush(); add_timeline(db, row, 'Created', payload.description, _actor(principal), status_to='Open')
    add_audit_event(db, request, principal, org.id, 'operations.incident.create', 'OperationalIncident', str(row.id), after=payload.model_dump(mode='json'))
    db.commit(); db.refresh(row); return row


@router.get('/operations/incidents', response_model=list[IncidentRead])
def list_incidents(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)], status: str | None = None, severity: str | None = None):
    _, site = _org_site(db); stmt = select(OperationalIncident).where(OperationalIncident.site_id == site.id)
    if status: stmt = stmt.where(OperationalIncident.status == status)
    if severity: stmt = stmt.where(OperationalIncident.severity == severity)
    return list(db.scalars(stmt.order_by(OperationalIncident.detected_at.desc())).all())


@router.post('/operations/incidents/{incident_id}/transition', response_model=IncidentRead)
def incident_transition(incident_id: UUID, payload: IncidentTransition, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles('SystemAdmin','PharmacyDirector','AccreditationLead','MedicationSafety','CAPAVerifier'))]):
    org, _ = _org_site(db); row = _incident(db, incident_id); before = {'status': row.status}
    transition_incident(db, row, payload, _actor(principal)); add_audit_event(db, request, principal, org.id, 'operations.incident.transition', 'OperationalIncident', str(row.id), before=before, after=payload.model_dump(mode='json'))
    db.commit(); db.refresh(row); return row


@router.post('/operations/incidents/{incident_id}/timeline', response_model=TimelineRead, status_code=201)
def timeline_add(incident_id: UUID, payload: TimelineCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles('SystemAdmin','PharmacyDirector','AccreditationLead','MedicationSafety','EvidenceReviewer'))]):
    org, _ = _org_site(db); incident = _incident(db, incident_id); row = add_timeline(db, incident, payload.event_type, payload.note, _actor(principal), evidence_reference=payload.evidence_reference)
    add_audit_event(db, request, principal, org.id, 'operations.incident.timeline', 'IncidentTimelineEntry', str(row.id), after=payload.model_dump())
    db.commit(); db.refresh(row); return row


@router.get('/operations/incidents/{incident_id}/timeline', response_model=list[TimelineRead])
def timeline_list(incident_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _incident(db, incident_id); return list(db.scalars(select(IncidentTimelineEntry).where(IncidentTimelineEntry.incident_id == incident_id).order_by(IncidentTimelineEntry.occurred_at)).all())


@router.post('/operations/cutovers', response_model=CutoverRead, status_code=201)
def create_cutover(payload: CutoverCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles('SystemAdmin','PharmacyDirector','AccreditationLead'))]):
    org, _ = _org_site(db); env = db.get(DeploymentEnvironment, payload.environment_id)
    if not env: raise HTTPException(404, 'Deployment environment not found')
    if payload.pilot_cycle_id and not db.get(PilotCycle, payload.pilot_cycle_id): raise HTTPException(404, 'Pilot cycle not found')
    existing = db.scalar(select(CutoverRun).where(CutoverRun.environment_id == env.id, CutoverRun.code == payload.code))
    if existing: return existing
    row = CutoverRun(created_by=_actor(principal), **payload.model_dump()); db.add(row); db.flush(); ensure_cutover_tasks(db, row); evaluate_cutover(db, row)
    add_audit_event(db, request, principal, org.id, 'operations.cutover.create', 'CutoverRun', str(row.id), after=payload.model_dump(mode='json'))
    db.commit(); db.refresh(row); return row


@router.get('/operations/cutovers/{run_id}')
def cutover_detail(run_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    row = _cutover(db, run_id); summary = evaluate_cutover(db, row); tasks = list(db.scalars(select(CutoverTask).where(CutoverTask.cutover_run_id == row.id).order_by(CutoverTask.sequence)).all()); db.commit()
    return {'cutover': CutoverRead.model_validate(row).model_dump(mode='json'), 'summary': summary, 'tasks': [CutoverTaskRead.model_validate(x).model_dump(mode='json') for x in tasks]}


@router.patch('/operations/cutovers/{run_id}/tasks/{task_code}', response_model=CutoverTaskRead)
def update_cutover_task(run_id: UUID, task_code: str, payload: CutoverTaskUpdate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles('SystemAdmin','PharmacyDirector','AccreditationLead','MedicationSafety','EvidenceReviewer','ReadOnlyAuditor'))]):
    org, _ = _org_site(db); run = _cutover(db, run_id); ensure_cutover_tasks(db, run); row = db.scalar(select(CutoverTask).where(CutoverTask.cutover_run_id == run.id, CutoverTask.code == task_code))
    if not row: raise HTTPException(404, 'Cutover task not found')
    before = {'status': row.status}; row.status = payload.status; row.evidence_reference = payload.evidence_reference; row.details = payload.details
    now = datetime.now(timezone.utc)
    if payload.status == 'InProgress' and not row.started_at: row.started_at = now
    if payload.status in {'Pass','Fail','Skipped','Blocked'}: row.completed_at = now; row.completed_by = _actor(principal)
    evaluate_cutover(db, run); add_audit_event(db, request, principal, org.id, 'operations.cutover.task.update', 'CutoverTask', str(row.id), before=before, after=payload.model_dump())
    db.commit(); db.refresh(row); return row


@router.post('/operations/cutovers/{run_id}/evaluate')
def evaluate_cutover_endpoint(run_id: UUID, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles('SystemAdmin','PharmacyDirector','AccreditationLead'))]):
    org, _ = _org_site(db); run = _cutover(db, run_id); summary = evaluate_cutover(db, run); add_audit_event(db, request, principal, org.id, 'operations.cutover.evaluate', 'CutoverRun', str(run.id), after=summary); db.commit(); return summary


@router.post('/operations/cutovers/{run_id}/decision', response_model=CutoverRead)
def cutover_decision(run_id: UUID, payload: CutoverDecision, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles('PharmacyDirector','SystemAdmin'))]):
    org, _ = _org_site(db); run = _cutover(db, run_id); before = {'decision': run.decision, 'status': run.status}; decide_cutover(db, run, payload.decision, payload.rationale, _actor(principal)); add_audit_event(db, request, principal, org.id, 'operations.cutover.decision', 'CutoverRun', str(run.id), before=before, after=payload.model_dump()); db.commit(); db.refresh(run); return run


@router.post('/operations/baselines', response_model=BaselineRead, status_code=201)
def create_baseline_release(payload: BaselineCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles('SystemAdmin','AccreditationLead','MedicationSafety'))]):
    org, site = _org_site(db); snapshot = db.get(ReadinessSnapshot, payload.snapshot_id)
    if not snapshot or snapshot.site_id != site.id: raise HTTPException(404, 'Readiness snapshot not found for site')
    row = create_baseline(db, site.id, snapshot, payload.code, payload.classification); add_audit_event(db, request, principal, org.id, 'operations.baseline.create', 'BaselineRelease', str(row.id), after=payload.model_dump(mode='json')); db.commit(); db.refresh(row); return row


@router.post('/operations/baselines/{release_id}/approve', response_model=BaselineRead)
def approve_baseline(release_id: UUID, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles('PharmacyDirector','AccreditationLead'))]):
    org, _ = _org_site(db); row = db.get(BaselineRelease, release_id)
    if not row: raise HTTPException(404, 'Baseline release not found')
    if row.status not in {'Draft','Approved'}: raise HTTPException(409, 'Only Draft baseline can be approved')
    row.status = 'Approved'; row.approved_by = _actor(principal); row.approved_at = datetime.now(timezone.utc); add_audit_event(db, request, principal, org.id, 'operations.baseline.approve', 'BaselineRelease', str(row.id), after={'status':'Approved'}); db.commit(); db.refresh(row); return row


@router.post('/operations/baselines/{release_id}/publish', response_model=BaselineRead)
def publish_baseline_release(release_id: UUID, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles('PharmacyDirector','AccreditationLead','ReadOnlyAuditor'))]):
    org, _ = _org_site(db); row = db.get(BaselineRelease, release_id)
    if not row: raise HTTPException(404, 'Baseline release not found')
    publish_baseline(db, row, _actor(principal)); add_audit_event(db, request, principal, org.id, 'operations.baseline.publish', 'BaselineRelease', str(row.id), after={'uri':row.release_uri,'sha256':row.release_sha256}); db.commit(); db.refresh(row); return row


@router.get('/operations/baselines', response_model=list[BaselineRead])
def list_baselines(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _, site = _org_site(db); return list(db.scalars(select(BaselineRelease).where(BaselineRelease.site_id == site.id).order_by(BaselineRelease.created_at.desc())).all())


@router.get('/operations/command-center')
def command_center(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _, site = _org_site(db); ensure_default_slos(db, site.id)
    slos = list(db.scalars(select(ServiceLevelObjective).where(ServiceLevelObjective.site_id == site.id, ServiceLevelObjective.active.is_(True))).all())
    latest_measurements = []
    for slo in slos:
        m = db.scalar(select(ServiceLevelMeasurement).where(ServiceLevelMeasurement.objective_id == slo.id).order_by(ServiceLevelMeasurement.window_end.desc()).limit(1))
        latest_measurements.append({'code':slo.code,'target':f'{slo.target_operator}{slo.target_value} {slo.unit}','value':m.measured_value if m else None,'status':m.status if m else 'Pending'})
    incidents = list(db.scalars(select(OperationalIncident).where(OperationalIncident.site_id == site.id, OperationalIncident.status != 'Closed').order_by(OperationalIncident.severity, OperationalIncident.detected_at.desc())).all())
    latest_cutover = db.scalar(select(CutoverRun).join(DeploymentEnvironment, DeploymentEnvironment.id == CutoverRun.environment_id).where(DeploymentEnvironment.site_id == site.id).order_by(CutoverRun.created_at.desc()).limit(1))
    latest_baseline = db.scalar(select(BaselineRelease).where(BaselineRelease.site_id == site.id).order_by(BaselineRelease.created_at.desc()).limit(1))
    db.commit()
    return {
        'slo': latest_measurements,
        'open_incidents': [IncidentRead.model_validate(x).model_dump(mode='json') for x in incidents],
        'cutover': CutoverRead.model_validate(latest_cutover).model_dump(mode='json') if latest_cutover else None,
        'baseline': BaselineRead.model_validate(latest_baseline).model_dump(mode='json') if latest_baseline else None,
        'operational_ready': not any(x.severity in {'P0','P1'} for x in incidents) and all(x['status'] == 'Pass' for x in latest_measurements if x['value'] is not None),
    }
