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
    Organization, Site, MeasurableElement, AssuranceProgram, AssuranceControl,
    AssuranceCycle, AssuranceTask, DataQualityRule, DataQualityRun, DataQualityIssue,
    RolloutWave, RolloutWaveSite,
)
from app.schemas.assurance import (
    AssuranceProgramRead, AssuranceControlRead, AssuranceCycleCreate, AssuranceCycleRead,
    AssuranceTaskComplete, AssuranceTaskRead, DataQualityRunCreate, DataQualityRuleRead,
    DataQualityRunRead, DataQualityIssueRead, RolloutWaveCreate, RolloutWaveRead,
    RolloutSiteCreate, RolloutSiteGateUpdate, RolloutWaveSiteRead,
)
from app.services.assurance_control import (
    ensure_p0_program, open_cycle, complete_task, close_cycle, ensure_dq_rules,
    execute_dq_run, create_rollout_wave, add_rollout_site, update_rollout_site,
    update_wave_summary,
)

router = APIRouter()


def _actor(principal: Principal):
    try:
        return UUID(principal.user_id)
    except (ValueError, TypeError):
        return None


def _org_site(db: Session):
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.code == settings.organization_code))
    if not org:
        raise HTTPException(409, "Baseline organization is not seeded")
    site = db.scalar(select(Site).where(Site.organization_id == org.id, Site.code == settings.default_site_code))
    if not site:
        raise HTTPException(404, "Site not found")
    return org, site


def _program(db: Session, program_id: UUID):
    row = db.get(AssuranceProgram, program_id)
    if not row:
        raise HTTPException(404, "Assurance program not found")
    return row


def _cycle(db: Session, cycle_id: UUID):
    row = db.get(AssuranceCycle, cycle_id)
    if not row:
        raise HTTPException(404, "Assurance cycle not found")
    return row


def _task(db: Session, task_id: UUID):
    row = db.get(AssuranceTask, task_id)
    if not row:
        raise HTTPException(404, "Assurance task not found")
    return row


@router.post("/assurance/programs/bootstrap-p0")
def bootstrap_p0_program(request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("AccreditationLead", "MedicationSafety", "SystemAdmin"))]):
    org, site = _org_site(db)
    program, created = ensure_p0_program(db, site.id, _actor(principal))
    total = db.scalar(select(func.count(AssuranceControl.id)).where(AssuranceControl.program_id == program.id))
    add_audit_event(db, request, principal, org.id, "assurance.program.bootstrap", "AssuranceProgram", str(program.id), after={"created": created, "total": total})
    db.commit(); db.refresh(program)
    return {"program": AssuranceProgramRead.model_validate(program), "created": created, "total": total}


@router.get("/assurance/programs", response_model=list[AssuranceProgramRead])
def list_programs(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _, site = _org_site(db)
    return list(db.scalars(select(AssuranceProgram).where(AssuranceProgram.site_id == site.id).order_by(AssuranceProgram.code)).all())


@router.get("/assurance/programs/{program_id}/controls", response_model=list[AssuranceControlRead])
def list_controls(program_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _program(db, program_id)
    return list(db.scalars(select(AssuranceControl).where(AssuranceControl.program_id == program_id).order_by(AssuranceControl.code)).all())


@router.post("/assurance/programs/{program_id}/cycles", response_model=AssuranceCycleRead, status_code=201)
def create_cycle(program_id: UUID, payload: AssuranceCycleCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("AccreditationLead", "MedicationSafety", "SystemAdmin"))]):
    org, _ = _org_site(db); program = _program(db, program_id)
    row = open_cycle(db, program, payload.code, payload.period_label, payload.due_at, _actor(principal))
    add_audit_event(db, request, principal, org.id, "assurance.cycle.create", "AssuranceCycle", str(row.id), after=payload.model_dump(mode="json"))
    db.commit(); db.refresh(row); return row


@router.get("/assurance/cycles/{cycle_id}")
def get_cycle(cycle_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    cycle = _cycle(db, cycle_id)
    rows = db.execute(
        select(AssuranceTask, AssuranceControl, MeasurableElement.me_id)
        .join(AssuranceControl, AssuranceControl.id == AssuranceTask.control_id)
        .join(MeasurableElement, MeasurableElement.id == AssuranceControl.measurable_element_id)
        .where(AssuranceTask.cycle_id == cycle.id)
        .order_by(MeasurableElement.me_id)
    ).all()
    return {
        "cycle": AssuranceCycleRead.model_validate(cycle).model_dump(mode="json"),
        "tasks": [
            {
                **AssuranceTaskRead.model_validate(task).model_dump(mode="json"),
                "control_code": control.code, "me_id": me_id, "critical": control.critical,
                "owner_role_code": control.owner_role_code,
            }
            for task, control, me_id in rows
        ],
    }


@router.post("/assurance/tasks/{task_id}/complete", response_model=AssuranceTaskRead)
def complete_assurance_task(task_id: UUID, payload: AssuranceTaskComplete, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("EvidenceReviewer", "MEOwner", "MedicationSafety", "AccreditationLead"))]):
    org, _ = _org_site(db); task = _task(db, task_id)
    before = {"status": task.status, "result": task.result}
    complete_task(db, task, payload.result, payload.evidence_reference, payload.comment, _actor(principal))
    add_audit_event(db, request, principal, org.id, "assurance.task.complete", "AssuranceTask", str(task.id), before=before, after=payload.model_dump(mode="json"))
    db.commit(); db.refresh(task); return task


@router.post("/assurance/cycles/{cycle_id}/close", response_model=AssuranceCycleRead)
def close_assurance_cycle(cycle_id: UUID, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("AccreditationLead", "MedicationSafety"))]):
    org, _ = _org_site(db); cycle = _cycle(db, cycle_id)
    close_cycle(db, cycle)
    add_audit_event(db, request, principal, org.id, "assurance.cycle.close", "AssuranceCycle", str(cycle.id), after=cycle.summary_json)
    db.commit(); db.refresh(cycle); return cycle


@router.post("/assurance/data-quality/rules/bootstrap")
def bootstrap_dq_rules(request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead"))]):
    org, _ = _org_site(db); created = ensure_dq_rules(db)
    total = db.scalar(select(func.count(DataQualityRule.id)))
    add_audit_event(db, request, principal, org.id, "assurance.data_quality.bootstrap", "DataQualityRule", "catalog", after={"created": created, "total": total})
    db.commit(); return {"created": created, "total": total}


@router.get("/assurance/data-quality/rules", response_model=list[DataQualityRuleRead])
def list_dq_rules(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    ensure_dq_rules(db); db.commit()
    return list(db.scalars(select(DataQualityRule).order_by(DataQualityRule.code)).all())


@router.post("/assurance/data-quality/runs", response_model=DataQualityRunRead, status_code=201)
def create_dq_run(payload: DataQualityRunCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety"))]):
    org, site = _org_site(db); row = execute_dq_run(db, site.id, payload.code, _actor(principal))
    add_audit_event(db, request, principal, org.id, "assurance.data_quality.run", "DataQualityRun", str(row.id), after=row.summary_json)
    db.commit(); db.refresh(row); return row


@router.get("/assurance/data-quality/runs/{run_id}/issues", response_model=list[DataQualityIssueRead])
def list_dq_issues(run_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    run = db.get(DataQualityRun, run_id)
    if not run: raise HTTPException(404, "Data quality run not found")
    return list(db.scalars(select(DataQualityIssue).where(DataQualityIssue.run_id == run_id).order_by(DataQualityIssue.severity, DataQualityIssue.created_at)).all())


@router.get("/assurance/continuous-dashboard")
def continuous_dashboard(db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    _, site = _org_site(db)
    programs = list(db.scalars(select(AssuranceProgram).where(AssuranceProgram.site_id == site.id)).all())
    program_ids = [x.id for x in programs]
    controls = list(db.scalars(select(AssuranceControl).where(AssuranceControl.program_id.in_(program_ids))).all()) if program_ids else []
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    overdue = sum(bool(x.next_due_at and x.next_due_at < now) for x in controls)
    latest_run = db.scalar(select(DataQualityRun).where(DataQualityRun.site_id == site.id).order_by(DataQualityRun.created_at.desc()).limit(1))
    latest_cycle = db.scalar(select(AssuranceCycle).where(AssuranceCycle.program_id.in_(program_ids)).order_by(AssuranceCycle.created_at.desc()).limit(1)) if program_ids else None
    return {
        "programs": len(programs), "controls": len(controls), "overdue_controls": overdue,
        "latest_cycle": AssuranceCycleRead.model_validate(latest_cycle).model_dump(mode="json") if latest_cycle else None,
        "latest_data_quality": DataQualityRunRead.model_validate(latest_run).model_dump(mode="json") if latest_run else None,
        "continuous_assurance_ready": bool(programs) and overdue == 0 and bool(latest_run and latest_run.summary_json.get("quality_pass")),
    }


@router.post("/assurance/rollout-waves", response_model=RolloutWaveRead, status_code=201)
def create_wave(payload: RolloutWaveCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("AccreditationLead", "SystemAdmin", "PharmacyDirector"))]):
    org, site = _org_site(db)
    row = create_rollout_wave(db, org.id, site.id, payload.code, payload.name, payload.planned_start, payload.planned_end, payload.owner_role_code, _actor(principal))
    add_audit_event(db, request, principal, org.id, "assurance.rollout.create", "RolloutWave", str(row.id), after=payload.model_dump(mode="json"))
    db.commit(); db.refresh(row); return row


@router.post("/assurance/rollout-waves/{wave_id}/sites", response_model=RolloutWaveSiteRead, status_code=201)
def add_wave_site(wave_id: UUID, payload: RolloutSiteCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("AccreditationLead", "SystemAdmin"))]):
    org, _ = _org_site(db); wave = db.get(RolloutWave, wave_id)
    if not wave: raise HTTPException(404, "Rollout wave not found")
    row = add_rollout_site(db, wave, payload.site_code, payload.name_ar, payload.name_en, payload.site_type)
    update_wave_summary(db, wave)
    add_audit_event(db, request, principal, org.id, "assurance.rollout.site.add", "RolloutWaveSite", str(row.id), after=payload.model_dump())
    db.commit(); db.refresh(row); return row


@router.patch("/assurance/rollout-wave-sites/{row_id}/gates", response_model=RolloutWaveSiteRead)
def update_wave_site_gates(row_id: UUID, payload: RolloutSiteGateUpdate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("AccreditationLead", "SystemAdmin", "PharmacyDirector"))]):
    org, _ = _org_site(db); row = db.get(RolloutWaveSite, row_id)
    if not row: raise HTTPException(404, "Rollout wave site not found")
    update_rollout_site(row, **payload.model_dump()); wave = db.get(RolloutWave, row.wave_id); update_wave_summary(db, wave)
    add_audit_event(db, request, principal, org.id, "assurance.rollout.site.gates", "RolloutWaveSite", str(row.id), after=payload.model_dump())
    db.commit(); db.refresh(row); return row


@router.get("/assurance/rollout-waves/{wave_id}")
def get_wave(wave_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    wave = db.get(RolloutWave, wave_id)
    if not wave: raise HTTPException(404, "Rollout wave not found")
    rows = list(db.scalars(select(RolloutWaveSite).where(RolloutWaveSite.wave_id == wave_id).order_by(RolloutWaveSite.created_at)).all())
    update_wave_summary(db, wave); db.commit()
    return {"wave": RolloutWaveRead.model_validate(wave).model_dump(mode="json"), "sites": [RolloutWaveSiteRead.model_validate(x).model_dump(mode="json") for x in rows]}
