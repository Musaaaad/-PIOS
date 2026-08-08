from __future__ import annotations
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.audit import add_audit_event
from app.core.config import get_settings
from app.core.security import Principal, get_principal, require_roles
from app.db.session import get_db
from app.models.entities import (Organization,Site,DeploymentEnvironment,DeploymentAcceptanceRun,DeploymentAcceptanceCheck,BackupRestoreRun,OidcValidationRun,PilotCycle)
from app.schemas.deployment import (EnvironmentCreate,EnvironmentRead,AcceptanceRunCreate,AcceptanceRunRead,CheckUpdate,CheckRead,BackupRestoreCreate,BackupRestoreRead,OidcValidationCreate,OidcValidationRead)
from app.services.deployment_acceptance import (ensure_checks,execute_automated_checks,calculate_summary,summarize_checks,record_backup_result,record_oidc_result,write_report,utcnow,unmeasured_checks,not_assessed_summary,NOT_ASSESSED)

router=APIRouter()

EXECUTE_ROLES=('SystemAdmin','AccreditationLead')

def _actor(principal):
    try:return UUID(principal.user_id)
    except Exception:return None

def _org_site(db,site_code=None):
    s=get_settings(); org=db.scalar(select(Organization).where(Organization.code==s.organization_code))
    if not org: raise HTTPException(409,'Baseline organization is not seeded')
    site=db.scalar(select(Site).where(Site.organization_id==org.id,Site.code==(site_code or s.default_site_code)))
    if not site: raise HTTPException(404,'Site not found')
    return org,site

def _env(db,env_id):
    row=db.get(DeploymentEnvironment,env_id)
    if not row: raise HTTPException(404,'Deployment environment not found')
    return row

def _run(db,run_id):
    row=db.get(DeploymentAcceptanceRun,run_id)
    if not row: raise HTTPException(404,'Acceptance run not found')
    return row

def _default_environment(db):
    """The environment this deployment's acceptance screen speaks for.

    Deliberately tolerant: a missing organisation, site or environment is a
    perfectly ordinary state that must render as "not assessed", not as an
    error and never as a pass. Nothing is created here - registering an
    environment is an operator decision whose fields (environment_type,
    tls_enabled, object storage kind) feed gate results directly, so inventing
    one would fabricate the evidence the gates are supposed to measure.
    """
    s=get_settings(); org=db.scalar(select(Organization).where(Organization.code==s.organization_code))
    site=db.scalar(select(Site).where(Site.organization_id==org.id,Site.code==s.default_site_code)) if org else None
    q=select(DeploymentEnvironment).where(DeploymentEnvironment.active.is_(True))
    if site is not None: q=q.where(DeploymentEnvironment.site_id==site.id)
    return db.scalar(q.order_by(DeploymentEnvironment.created_at.desc()))

def _latest_run(db,env):
    return db.scalar(select(DeploymentAcceptanceRun).where(DeploymentAcceptanceRun.environment_id==env.id).order_by(DeploymentAcceptanceRun.created_at.desc()))

def _summary_payload(db,principal):
    """Everything the acceptance screen renders, sourced only from stored runs.

    There is no demo branch and no default-to-pass branch. When nothing has
    been measured the payload says assessed=False with a machine-readable
    reason, lists all 24 catalog gates as NotAssessed, and reports
    deployment_ready=False.
    """
    can_execute=bool(set(principal.roles)&set(EXECUTE_ROLES))
    env=_default_environment(db)
    catalog=unmeasured_checks()
    base={'assessed':False,'can_execute':can_execute,'environment':None,'run':None,
          'checks':catalog,'backup_restore':None,'oidc_validation':None,
          'catalog_total':len(catalog),'evaluated_at':None}
    if env is None:
        base['summary']=not_assessed_summary('no_environment'); base['reason']='no_environment'; return base
    base['environment']=EnvironmentRead.model_validate(env).model_dump(mode='json')
    backups=db.scalar(select(BackupRestoreRun).where(BackupRestoreRun.environment_id==env.id).order_by(BackupRestoreRun.created_at.desc()))
    oidc=db.scalar(select(OidcValidationRun).where(OidcValidationRun.environment_id==env.id).order_by(OidcValidationRun.created_at.desc()))
    base['backup_restore']=BackupRestoreRead.model_validate(backups).model_dump(mode='json') if backups else None
    base['oidc_validation']=OidcValidationRead.model_validate(oidc).model_dump(mode='json') if oidc else None
    run=_latest_run(db,env)
    if run is None:
        base['summary']=not_assessed_summary('no_run'); base['reason']='no_run'; return base
    rows=list(db.scalars(select(DeploymentAcceptanceCheck).where(DeploymentAcceptanceCheck.run_id==run.id).order_by(DeploymentAcceptanceCheck.category,DeploymentAcceptanceCheck.check_code)).all())
    if not rows:
        # A run exists but was never populated. Reporting its empty rollup would
        # score zero required blockers and therefore read as "Pass".
        base['run']=AcceptanceRunRead.model_validate(run).model_dump(mode='json')
        base['summary']=not_assessed_summary('run_has_no_checks'); base['reason']='run_has_no_checks'; return base
    base['assessed']=True; base['reason']=None
    base['run']=AcceptanceRunRead.model_validate(run).model_dump(mode='json')
    base['summary']=summarize_checks(rows)
    base['checks']=[CheckRead.model_validate(x).model_dump(mode='json') for x in rows]
    base['evaluated_at']=(run.completed_at or run.started_at).isoformat() if (run.completed_at or run.started_at) else None
    return base

@router.get('/deployment/acceptance-summary')
def acceptance_summary(db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(get_principal)]):
    return _summary_payload(db,principal)

@router.post('/deployment/acceptance-summary/evaluate')
def evaluate_acceptance(request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles(*EXECUTE_ROLES))]):
    """Measure the automated gates NOW and store the result as a new run.

    This is the only path that changes a gate's value. Reading the summary
    re-reads what was stored; only this recomputes, which is why the two are
    separate verbs and separate buttons.
    """
    org,_=_org_site(db)
    env=_default_environment(db)
    if env is None:
        raise HTTPException(409,'No deployment environment is registered. An administrator must register one before acceptance can be evaluated.')
    run_code=f"LIVE-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run=db.scalar(select(DeploymentAcceptanceRun).where(DeploymentAcceptanceRun.environment_id==env.id,DeploymentAcceptanceRun.run_code==run_code))
    if run is None:
        run=DeploymentAcceptanceRun(environment_id=env.id,run_code=run_code,scope='PostDeploy',status='Draft',outcome=NOT_ASSESSED,initiated_by=_actor(principal))
        db.add(run); db.flush(); ensure_checks(db,run)
        # Commit before measuring. execute_automated_checks() inspects the
        # engine for SCHEMA_TABLES_PRESENT, which checks out its own
        # connection; on a shared connection that discards this transaction's
        # un-committed check rows and the later UPDATEs match nothing. The
        # existing create-then-execute flow never hit this only because those
        # are two requests with a commit between them.
        db.commit(); db.refresh(run)
    summary=execute_automated_checks(db,run,env)
    checks=list(db.scalars(select(DeploymentAcceptanceCheck).where(DeploymentAcceptanceCheck.run_id==run.id).order_by(DeploymentAcceptanceCheck.check_code)).all())
    path,sha=write_report(run,checks)
    add_audit_event(db,request,principal,org.id,'deployment.acceptance.evaluate','DeploymentAcceptanceRun',str(run.id),after={'summary':summary,'report':str(path),'sha256':sha})
    db.commit()
    return _summary_payload(db,principal)

@router.post('/deployment/environments',response_model=EnvironmentRead,status_code=201)
def create_environment(payload:EnvironmentCreate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','AccreditationLead','PharmacyDirector'))]):
    org,site=_org_site(db,payload.site_code); existing=db.scalar(select(DeploymentEnvironment).where(DeploymentEnvironment.site_id==site.id,DeploymentEnvironment.code==payload.code))
    if existing:return existing
    row=DeploymentEnvironment(site_id=site.id,code=payload.code,name=payload.name,environment_type=payload.environment_type,api_base_url=payload.api_base_url,frontend_base_url=payload.frontend_base_url,database_kind=payload.database_kind,database_version=payload.database_version,object_storage_kind=payload.object_storage_kind,auth_mode=payload.auth_mode,oidc_issuer=payload.oidc_issuer,release_version=payload.release_version,release_sha=payload.release_sha,tls_enabled=payload.tls_enabled,monitoring_enabled=payload.monitoring_enabled,backup_policy_ref=payload.backup_policy_ref,status='Registered')
    db.add(row);db.flush();add_audit_event(db,request,principal,org.id,'deployment.environment.create','DeploymentEnvironment',str(row.id),after=payload.model_dump(mode='json'));db.commit();db.refresh(row);return row

@router.get('/deployment/environments',response_model=list[EnvironmentRead])
def list_environments(db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    return db.scalars(select(DeploymentEnvironment).order_by(DeploymentEnvironment.created_at.desc())).all()

@router.get('/deployment/environments/{environment_id}')
def environment_detail(environment_id:UUID,db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    env=_env(db,environment_id); runs=list(db.scalars(select(DeploymentAcceptanceRun).where(DeploymentAcceptanceRun.environment_id==env.id).order_by(DeploymentAcceptanceRun.created_at.desc())).all()); backups=list(db.scalars(select(BackupRestoreRun).where(BackupRestoreRun.environment_id==env.id).order_by(BackupRestoreRun.created_at.desc())).all()); oidc=list(db.scalars(select(OidcValidationRun).where(OidcValidationRun.environment_id==env.id).order_by(OidcValidationRun.created_at.desc())).all())
    latest=runs[0] if runs else None
    return {'environment':EnvironmentRead.model_validate(env).model_dump(mode='json'),'latest_acceptance':AcceptanceRunRead.model_validate(latest).model_dump(mode='json') if latest else None,'backup_restore_runs':[BackupRestoreRead.model_validate(x).model_dump(mode='json') for x in backups],'oidc_validations':[OidcValidationRead.model_validate(x).model_dump(mode='json') for x in oidc]}

@router.post('/deployment/environments/{environment_id}/acceptance-runs',response_model=AcceptanceRunRead,status_code=201)
def create_run(environment_id:UUID,payload:AcceptanceRunCreate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','AccreditationLead','PharmacyDirector'))]):
    org,_=_org_site(db);env=_env(db,environment_id); existing=db.scalar(select(DeploymentAcceptanceRun).where(DeploymentAcceptanceRun.environment_id==env.id,DeploymentAcceptanceRun.run_code==payload.run_code))
    if existing:return existing
    if payload.pilot_cycle_id and not db.get(PilotCycle,payload.pilot_cycle_id):raise HTTPException(404,'Pilot cycle not found')
    row=DeploymentAcceptanceRun(environment_id=env.id,pilot_cycle_id=payload.pilot_cycle_id,run_code=payload.run_code,scope=payload.scope,status='Draft',outcome='NotAssessed',initiated_by=_actor(principal));db.add(row);db.flush();ensure_checks(db,row);add_audit_event(db,request,principal,org.id,'deployment.acceptance.create','DeploymentAcceptanceRun',str(row.id),after=payload.model_dump(mode='json'));db.commit();db.refresh(row);return row

@router.post('/deployment/acceptance-runs/{run_id}/execute-automated')
def execute(run_id:UUID,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','AccreditationLead'))]):
    org,_=_org_site(db);run=_run(db,run_id);env=_env(db,run.environment_id);summary=execute_automated_checks(db,run,env);checks=list(db.scalars(select(DeploymentAcceptanceCheck).where(DeploymentAcceptanceCheck.run_id==run.id).order_by(DeploymentAcceptanceCheck.check_code)).all());path,sha=write_report(run,checks);add_audit_event(db,request,principal,org.id,'deployment.acceptance.execute','DeploymentAcceptanceRun',str(run.id),after={'summary':summary,'report':str(path),'sha256':sha});db.commit();return {'run':AcceptanceRunRead.model_validate(run).model_dump(mode='json'),'checks':[CheckRead.model_validate(x).model_dump(mode='json') for x in checks]}

@router.patch('/deployment/acceptance-runs/{run_id}/checks/{check_code}',response_model=CheckRead)
def update_check(run_id:UUID,check_code:str,payload:CheckUpdate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','AccreditationLead','PharmacyDirector','MedicationSafety','CAPAVerifier'))]):
    org,_=_org_site(db);run=_run(db,run_id);ensure_checks(db,run);row=db.scalar(select(DeploymentAcceptanceCheck).where(DeploymentAcceptanceCheck.run_id==run.id,DeploymentAcceptanceCheck.check_code==check_code))
    if not row:raise HTTPException(404,'Acceptance check not found')
    before={'status':row.status};row.status=payload.status;row.measured_value=payload.measured_value;row.evidence_reference=payload.evidence_reference;row.details=payload.details;row.checked_by=_actor(principal);row.checked_at=utcnow();calculate_summary(db,run);checks=list(db.scalars(select(DeploymentAcceptanceCheck).where(DeploymentAcceptanceCheck.run_id==run.id)).all());write_report(run,checks);add_audit_event(db,request,principal,org.id,'deployment.acceptance.check.update','DeploymentAcceptanceCheck',str(row.id),before=before,after=payload.model_dump(mode='json'));db.commit();db.refresh(row);return row

@router.get('/deployment/acceptance-runs/{run_id}')
def run_detail(run_id:UUID,db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    run=_run(db,run_id);ensure_checks(db,run);summary=calculate_summary(db,run);checks=list(db.scalars(select(DeploymentAcceptanceCheck).where(DeploymentAcceptanceCheck.run_id==run.id).order_by(DeploymentAcceptanceCheck.category,DeploymentAcceptanceCheck.check_code)).all());return {'run':AcceptanceRunRead.model_validate(run).model_dump(mode='json'),'summary':summary,'checks':[CheckRead.model_validate(x).model_dump(mode='json') for x in checks]}

@router.post('/deployment/environments/{environment_id}/backup-restore-runs',response_model=BackupRestoreRead,status_code=201)
def backup_result(environment_id:UUID,payload:BackupRestoreCreate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','PharmacyDirector'))]):
    org,_=_org_site(db);env=_env(db,environment_id);row=record_backup_result(db,env,payload,_actor(principal));add_audit_event(db,request,principal,org.id,'deployment.backup_restore.record','BackupRestoreRun',str(row.id),after=payload.model_dump(mode='json'));db.commit();db.refresh(row);return row

@router.post('/deployment/environments/{environment_id}/oidc-validations',response_model=OidcValidationRead,status_code=201)
def oidc_result(environment_id:UUID,payload:OidcValidationCreate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','PharmacyDirector'))]):
    org,_=_org_site(db);env=_env(db,environment_id);row=record_oidc_result(db,env,payload,_actor(principal));add_audit_event(db,request,principal,org.id,'deployment.oidc.record','OidcValidationRun',str(row.id),after=payload.model_dump(mode='json'));db.commit();db.refresh(row);return row
