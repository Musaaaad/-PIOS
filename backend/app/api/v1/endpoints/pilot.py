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
from app.models.entities import (
    Organization, Site, User, Role, UserRole, PilotCycle, PilotParticipant, PilotGateCheck,
    UatScenario, UatExecution, PilotDecision,
)
from app.schemas.pilot import (
    PilotCreate, PilotRead, ParticipantCreate, ParticipantRead, GateUpdate, GateRead,
    PilotLifecycle, UatScenarioRead, UatExecutionCreate, UatExecutionRead,
    DecisionCreate, DecisionRead,
)
from app.services.pilot_control import (
    GATE_CATALOG, ensure_gate_rows, bootstrap_p0_campaign, pilot_readiness, transition_pilot,
    uat_summary, now_utc,
)

router=APIRouter()


def _actor_uuid(principal: Principal):
    try: return UUID(principal.user_id)
    except (ValueError,TypeError): return None


def _org_site(db: Session, site_code: str|None=None):
    s=get_settings(); org=db.scalar(select(Organization).where(Organization.code==s.organization_code))
    if not org: raise HTTPException(status_code=409,detail="Baseline organization is not seeded")
    site=db.scalar(select(Site).where(Site.organization_id==org.id, Site.code==(site_code or s.default_site_code)))
    if not site: raise HTTPException(status_code=404,detail="Site not found")
    return org,site


def _pilot(db: Session,pilot_id: UUID):
    row=db.get(PilotCycle,pilot_id)
    if not row: raise HTTPException(status_code=404,detail="Pilot cycle not found")
    return row


@router.post('/pilot-cycles',response_model=PilotRead,status_code=201)
def create_pilot(payload:PilotCreate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','AccreditationLead','PharmacyDirector'))]):
    org,site=_org_site(db,payload.site_code)
    existing=db.scalar(select(PilotCycle).where(PilotCycle.site_id==site.id,PilotCycle.code==payload.code))
    if existing: return existing
    row=PilotCycle(site_id=site.id,code=payload.code,name=payload.name,objective=payload.objective,scope_json=payload.scope_json,period_start=payload.period_start,period_end=payload.period_end,status='Draft',owner_role_code=payload.owner_role_code)
    db.add(row);db.flush();ensure_gate_rows(db,row)
    add_audit_event(db,request,principal,org.id,'pilot.create','PilotCycle',str(row.id),after=payload.model_dump(mode='json'))
    db.commit();db.refresh(row);return row


@router.get('/pilot-cycles',response_model=list[PilotRead])
def list_pilots(db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    return db.scalars(select(PilotCycle).order_by(PilotCycle.created_at.desc())).all()


@router.get('/pilot-cycles/{pilot_id}')
def pilot_detail(pilot_id:UUID,db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    row=_pilot(db,pilot_id);ensure_gate_rows(db,row)
    participants=list(db.scalars(select(PilotParticipant).where(PilotParticipant.pilot_cycle_id==row.id)).all())
    decisions=list(db.scalars(select(PilotDecision).where(PilotDecision.pilot_cycle_id==row.id).order_by(PilotDecision.created_at.desc())).all())
    return {'pilot':PilotRead.model_validate(row).model_dump(mode='json'),'readiness':pilot_readiness(db,row),'participants':[ParticipantRead.model_validate(x).model_dump(mode='json') for x in participants],'decisions':[DecisionRead.model_validate(x).model_dump(mode='json') for x in decisions]}


@router.post('/pilot-cycles/{pilot_id}/participants',response_model=ParticipantRead,status_code=201)
def provision_participant(pilot_id:UUID,payload:ParticipantCreate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','AccreditationLead','PharmacyDirector'))]):
    org,site=_org_site(db);pilot=_pilot(db,pilot_id)
    roles=list(db.scalars(select(Role).where(Role.code.in_(payload.role_codes))).all()); found={x.code for x in roles}
    missing=sorted(set(payload.role_codes)-found)
    if missing: raise HTTPException(status_code=422,detail={'unknown_roles':missing})
    user=db.scalar(select(User).where(User.email==payload.email.lower()))
    if not user:
        user=User(organization_id=org.id,email=payload.email.lower(),display_name=payload.display_name,active=True);db.add(user);db.flush()
    else:
        user.display_name=payload.display_name;user.active=True
    for role in roles:
        ur=db.scalar(select(UserRole).where(UserRole.user_id==user.id,UserRole.role_id==role.id,UserRole.site_id==site.id))
        if not ur: db.add(UserRole(user_id=user.id,role_id=role.id,site_id=site.id))
    row=db.scalar(select(PilotParticipant).where(PilotParticipant.pilot_cycle_id==pilot.id,PilotParticipant.user_id==user.id))
    if not row:
        row=PilotParticipant(pilot_cycle_id=pilot.id,user_id=user.id);db.add(row)
    row.external_subject=payload.external_subject;row.role_codes=sorted(set(payload.role_codes));row.training_status=payload.training_status;row.access_test_status=payload.access_test_status;row.active=True
    if row.training_status=='Complete' and row.access_test_status=='Pass': row.verified_at=now_utc()
    db.flush()
    add_audit_event(db,request,principal,org.id,'pilot.participant.provision','PilotParticipant',str(row.id),after=payload.model_dump(mode='json'))
    db.commit();db.refresh(row);return row


@router.patch('/pilot-cycles/{pilot_id}/gates/{gate_code}',response_model=GateRead)
def update_gate(pilot_id:UUID,gate_code:str,payload:GateUpdate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','AccreditationLead','PharmacyDirector','MedicationSafety'))]):
    org,_=_org_site(db);pilot=_pilot(db,pilot_id);ensure_gate_rows(db,pilot)
    valid={x[0] for x in GATE_CATALOG}
    if gate_code not in valid: raise HTTPException(status_code=404,detail='Unknown pilot gate')
    row=db.scalar(select(PilotGateCheck).where(PilotGateCheck.pilot_cycle_id==pilot.id,PilotGateCheck.gate_code==gate_code))
    before={'status':row.status};row.status=payload.status;row.evidence_reference=payload.evidence_reference;row.notes=payload.notes;row.checked_by=_actor_uuid(principal);row.checked_at=now_utc()
    add_audit_event(db,request,principal,org.id,'pilot.gate.update','PilotGateCheck',str(row.id),before=before,after=payload.model_dump(mode='json'))
    db.commit();db.refresh(row);return row


@router.post('/pilot-cycles/{pilot_id}/bootstrap-p0')
def bootstrap_p0(pilot_id:UUID,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','AccreditationLead','PharmacyDirector'))]):
    org,_=_org_site(db);pilot=_pilot(db,pilot_id);ensure_gate_rows(db,pilot)
    campaign,created=bootstrap_p0_campaign(db,pilot,datetime.combine(pilot.period_end,datetime.min.time(),tzinfo=timezone.utc))
    add_audit_event(db,request,principal,org.id,'pilot.p0.bootstrap','EvidenceCampaign',str(campaign.id),after={'created':created,'expected_total':48})
    db.commit();return {'campaign_id':str(campaign.id),'created':created,'total':48,'status':campaign.status}


@router.post('/pilot-cycles/{pilot_id}/lifecycle',response_model=PilotRead)
def lifecycle(pilot_id:UUID,payload:PilotLifecycle,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','AccreditationLead','PharmacyDirector'))]):
    org,_=_org_site(db);pilot=_pilot(db,pilot_id);before={'status':pilot.status};transition_pilot(db,pilot,payload.to_status)
    if payload.to_status=='RolledBack': pilot.rollback_reason=payload.comment or 'Pilot rolled back by authorized user'
    add_audit_event(db,request,principal,org.id,'pilot.lifecycle','PilotCycle',str(pilot.id),before=before,after={'status':pilot.status,'comment':payload.comment})
    db.commit();db.refresh(pilot);return pilot


@router.get('/pilot-cycles/{pilot_id}/readiness')
def readiness(pilot_id:UUID,db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    return pilot_readiness(db,_pilot(db,pilot_id))


@router.get('/uat-scenarios',response_model=list[UatScenarioRead])
def scenarios(db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    return db.scalars(select(UatScenario).where(UatScenario.active.is_(True)).order_by(UatScenario.code)).all()


@router.post('/pilot-cycles/{pilot_id}/uat-executions',response_model=UatExecutionRead,status_code=201)
def record_uat(pilot_id:UUID,payload:UatExecutionCreate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','AccreditationLead','ReadOnlyAuditor','EvidenceReviewer','CAPAVerifier'))]):
    org,_=_org_site(db);pilot=_pilot(db,pilot_id);scenario=db.scalar(select(UatScenario).where(UatScenario.code==payload.scenario_code,UatScenario.active.is_(True)))
    if not scenario: raise HTTPException(status_code=404,detail='UAT scenario not found')
    if payload.status=='Pass' and payload.defect_severity: raise HTTPException(status_code=422,detail='Passed UAT cannot have defect severity')
    if payload.status in {'Fail','Blocked'} and not payload.actual_result: raise HTTPException(status_code=422,detail='Failed or blocked UAT requires actual_result')
    existing=db.scalar(select(UatExecution).where(UatExecution.pilot_cycle_id==pilot.id,UatExecution.scenario_id==scenario.id,UatExecution.attempt==payload.attempt))
    row=existing or UatExecution(pilot_cycle_id=pilot.id,scenario_id=scenario.id,attempt=payload.attempt)
    if not existing: db.add(row)
    row.executor_user_id=_actor_uuid(principal);row.status=payload.status;row.actual_result=payload.actual_result;row.defect_severity=payload.defect_severity;row.defect_reference=payload.defect_reference;row.evidence_reference=payload.evidence_reference;row.executed_at=now_utc()
    db.flush(); summary=uat_summary(db,pilot.id)
    gate=db.scalar(select(PilotGateCheck).where(PilotGateCheck.pilot_cycle_id==pilot.id,PilotGateCheck.gate_code=='UAT_CRITICAL_PASS'))
    if gate:
        gate.status='Pass' if summary['critical_failures']==0 and summary['not_run']==0 and summary['pass_rate']>=90 else ('Fail' if summary['critical_failures'] else 'Pending')
        gate.evidence_reference=f"uat-pass-rate:{summary['pass_rate']}%;critical-failures:{summary['critical_failures']}";gate.checked_at=now_utc()
    add_audit_event(db,request,principal,org.id,'pilot.uat.record','UatExecution',str(row.id),after=payload.model_dump(mode='json'))
    db.commit();db.refresh(row);return row


@router.get('/pilot-cycles/{pilot_id}/uat-summary')
def get_uat_summary(pilot_id:UUID,db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    _pilot(db,pilot_id);return uat_summary(db,pilot_id)


@router.post('/pilot-cycles/{pilot_id}/decisions',response_model=DecisionRead,status_code=201)
def create_decision(pilot_id:UUID,payload:DecisionCreate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','AccreditationLead','PharmacyDirector'))]):
    org,_=_org_site(db);pilot=_pilot(db,pilot_id);ready=pilot_readiness(db,pilot)
    if payload.decision=='Go' and not ready['go_live_ready']:
        raise HTTPException(status_code=409,detail={'message':'Go decision blocked','blockers':ready['blockers']})
    if payload.decision=='ConditionalGo' and not payload.conditions:
        raise HTTPException(status_code=422,detail='ConditionalGo requires conditions')
    row=PilotDecision(pilot_cycle_id=pilot.id,decision=payload.decision,rationale=payload.rationale,conditions=payload.conditions,decided_by=_actor_uuid(principal));db.add(row);db.flush()
    add_audit_event(db,request,principal,org.id,'pilot.decision.create','PilotDecision',str(row.id),after=payload.model_dump(mode='json'))
    db.commit();db.refresh(row);return row
