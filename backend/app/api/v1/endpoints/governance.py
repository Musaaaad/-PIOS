from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Request,Query
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.core.audit import add_audit_event
from app.core.config import get_settings
from app.core.security import Principal,get_principal,require_roles
from app.db.session import get_db
from app.models.entities import Organization,ReleasePackage,ReleaseArtifact,SecurityControlAssessment,RetentionPolicy,LegalHold,AuditExportPackage
from app.schemas.governance import *
from app.services.governance import bootstrap_controls,create_release,add_artifact,evaluate_release,approve_release,publish_release,place_hold,release_hold,purge_preview,create_audit_export,verify_audit_export
router=APIRouter()
def _actor(p):
    try:return UUID(p.user_id)
    except:return None
def _org(db):
    row=db.scalar(select(Organization).where(Organization.code==get_settings().organization_code))
    if not row:raise HTTPException(409,'Baseline organization is not seeded')
    return row
@router.post('/governance/security-controls/bootstrap')
def controls_bootstrap(request:Request,db:Annotated[Session,Depends(get_db)],p:Annotated[Principal,Depends(require_roles('SystemAdmin','PharmacyDirector'))]):
    org=_org(db);created=bootstrap_controls(db,org.id,_actor(p));add_audit_event(db,request,p,org.id,'governance.security.bootstrap','Organization',str(org.id),after={'created':len(created)});db.commit();return {'created':len(created),'total':db.scalar(select(func.count(SecurityControlAssessment.id)).where(SecurityControlAssessment.organization_id==org.id))}
@router.get('/governance/security-controls',response_model=list[SecurityControlRead])
def controls_list(db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    org=_org(db);return list(db.scalars(select(SecurityControlAssessment).where(SecurityControlAssessment.organization_id==org.id).order_by(SecurityControlAssessment.code)).all())
@router.patch('/governance/security-controls/{control_id}',response_model=SecurityControlRead)
def controls_update(control_id:UUID,payload:SecurityControlUpdate,request:Request,db:Annotated[Session,Depends(get_db)],p:Annotated[Principal,Depends(require_roles('SystemAdmin','PharmacyDirector','ReadOnlyAuditor'))]):
    org=_org(db);row=db.get(SecurityControlAssessment,control_id)
    if not row:raise HTTPException(404,'Security control not found')
    row.status=payload.status;row.evidence_reference=payload.evidence_reference;row.details=payload.details;row.checked_by=_actor(p);from app.services.governance import utcnow;row.checked_at=utcnow();add_audit_event(db,request,p,org.id,'governance.security.update','SecurityControlAssessment',str(row.id),after=payload.model_dump());db.commit();db.refresh(row);return row
@router.post('/governance/retention-policies',response_model=RetentionPolicyRead,status_code=201)
def retention_create(payload:RetentionPolicyCreate,request:Request,db:Annotated[Session,Depends(get_db)],p:Annotated[Principal,Depends(require_roles('SystemAdmin','PharmacyDirector'))]):
    org=_org(db);from app.services.governance import utcnow
    row=RetentionPolicy(organization_id=org.id,approved_by=_actor(p),approved_at=utcnow(),**payload.model_dump());db.add(row);add_audit_event(db,request,p,org.id,'governance.retention.create','RetentionPolicy',payload.code,after=payload.model_dump());db.commit();db.refresh(row);return row
@router.get('/governance/retention-policies',response_model=list[RetentionPolicyRead])
def retention_list(db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    org=_org(db);return list(db.scalars(select(RetentionPolicy).where(RetentionPolicy.organization_id==org.id).order_by(RetentionPolicy.code)).all())
@router.post('/governance/legal-holds',response_model=LegalHoldRead,status_code=201)
def hold_create(payload:LegalHoldCreate,request:Request,db:Annotated[Session,Depends(get_db)],p:Annotated[Principal,Depends(require_roles('SystemAdmin','PharmacyDirector'))]):
    org=_org(db);row=place_hold(db,org.id,payload,_actor(p));add_audit_event(db,request,p,org.id,'governance.legal_hold.place','LegalHold',str(row.id),after=payload.model_dump());db.commit();db.refresh(row);return row
@router.post('/governance/legal-holds/{hold_id}/release',response_model=LegalHoldRead)
def hold_release(hold_id:UUID,payload:LegalHoldRelease,request:Request,db:Annotated[Session,Depends(get_db)],p:Annotated[Principal,Depends(require_roles('PharmacyDirector','SystemAdmin'))]):
    org=_org(db);row=db.get(LegalHold,hold_id)
    if not row:raise HTTPException(404,'Legal hold not found')
    release_hold(row,payload.reason,_actor(p));add_audit_event(db,request,p,org.id,'governance.legal_hold.release','LegalHold',str(row.id),after=payload.model_dump());db.commit();db.refresh(row);return row
@router.get('/governance/purge-preview')
def preview(entity_type:str=Query(...,min_length=2,max_length=128),db:Annotated[Session,Depends(get_db)]=None,_:Annotated[Principal,Depends(require_roles('SystemAdmin','ReadOnlyAuditor'))]=None):
    org=_org(db);return purge_preview(db,org.id,entity_type)
@router.post('/governance/releases',response_model=ReleaseRead,status_code=201)
def release_create(payload:ReleaseCreate,request:Request,db:Annotated[Session,Depends(get_db)],p:Annotated[Principal,Depends(require_roles('SystemAdmin'))]):
    org=_org(db);row=create_release(db,org.id,payload.code,payload.version,payload.release_sha,_actor(p));add_audit_event(db,request,p,org.id,'governance.release.create','ReleasePackage',str(row.id),after=payload.model_dump());db.commit();db.refresh(row);return row
@router.post('/governance/releases/{release_id}/artifacts')
def artifact_create(release_id:UUID,payload:ArtifactCreate,request:Request,db:Annotated[Session,Depends(get_db)],p:Annotated[Principal,Depends(require_roles('SystemAdmin'))]):
    org=_org(db);pkg=db.get(ReleasePackage,release_id)
    if not pkg:raise HTTPException(404,'Release package not found')
    row,created=add_artifact(db,pkg,payload);add_audit_event(db,request,p,org.id,'governance.release.artifact','ReleaseArtifact',str(row.id),after={'created':created,'name':row.name,'sha256':row.sha256});db.commit();db.refresh(row);return {'created':created,'artifact':ArtifactRead.model_validate(row)}
@router.post('/governance/releases/{release_id}/evaluate')
def release_evaluate(release_id:UUID,request:Request,db:Annotated[Session,Depends(get_db)],p:Annotated[Principal,Depends(require_roles('SystemAdmin','ReadOnlyAuditor','PharmacyDirector'))]):
    org=_org(db);pkg=db.get(ReleasePackage,release_id)
    if not pkg:raise HTTPException(404,'Release package not found')
    result=evaluate_release(db,pkg);add_audit_event(db,request,p,org.id,'governance.release.evaluate','ReleasePackage',str(pkg.id),after=result);db.commit();return result
@router.post('/governance/releases/{release_id}/approve',response_model=ReleaseRead)
def release_approve(release_id:UUID,request:Request,db:Annotated[Session,Depends(get_db)],p:Annotated[Principal,Depends(require_roles('PharmacyDirector','ReadOnlyAuditor'))]):
    org=_org(db);pkg=db.get(ReleasePackage,release_id)
    if not pkg:raise HTTPException(404,'Release package not found')
    approve_release(db,pkg,_actor(p));add_audit_event(db,request,p,org.id,'governance.release.approve','ReleasePackage',str(pkg.id),after={'status':pkg.status});db.commit();db.refresh(pkg);return pkg
@router.post('/governance/releases/{release_id}/publish',response_model=ReleaseRead)
def release_publish(release_id:UUID,request:Request,db:Annotated[Session,Depends(get_db)],p:Annotated[Principal,Depends(require_roles('SystemAdmin'))]):
    org=_org(db);pkg=db.get(ReleasePackage,release_id)
    if not pkg:raise HTTPException(404,'Release package not found')
    publish_release(pkg,_actor(p));add_audit_event(db,request,p,org.id,'governance.release.publish','ReleasePackage',str(pkg.id),after={'status':pkg.status});db.commit();db.refresh(pkg);return pkg
@router.get('/governance/releases/{release_id}')
def release_detail(release_id:UUID,db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    pkg=db.get(ReleasePackage,release_id)
    if not pkg:raise HTTPException(404,'Release package not found')
    arts=list(db.scalars(select(ReleaseArtifact).where(ReleaseArtifact.release_package_id==pkg.id).order_by(ReleaseArtifact.artifact_type,ReleaseArtifact.name)).all());return {'release':ReleaseRead.model_validate(pkg),'artifacts':[ArtifactRead.model_validate(x) for x in arts]}
@router.post('/governance/audit-exports',response_model=AuditExportRead,status_code=201)
def audit_export_create(payload:AuditExportCreate,request:Request,db:Annotated[Session,Depends(get_db)],p:Annotated[Principal,Depends(require_roles('ReadOnlyAuditor','SystemAdmin'))]):
    org=_org(db);row=create_audit_export(db,org.id,payload.code,payload.period_start,payload.period_end,_actor(p));add_audit_event(db,request,p,org.id,'governance.audit_export.create','AuditExportPackage',str(row.id),after={'event_count':row.event_count,'root_hash':row.root_hash});db.commit();db.refresh(row);return row
@router.post('/governance/audit-exports/{export_id}/verify')
def audit_export_verify(export_id:UUID,request:Request,db:Annotated[Session,Depends(get_db)],p:Annotated[Principal,Depends(require_roles('ReadOnlyAuditor','SystemAdmin'))]):
    org=_org(db);row=db.get(AuditExportPackage,export_id)
    if not row:raise HTTPException(404,'Audit export not found')
    result=verify_audit_export(row,_actor(p));add_audit_event(db,request,p,org.id,'governance.audit_export.verify','AuditExportPackage',str(row.id),after=result);db.commit();return result
@router.get('/governance/summary')
def summary(db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    org=_org(db);controls=list(db.scalars(select(SecurityControlAssessment).where(SecurityControlAssessment.organization_id==org.id)).all());latest=db.scalar(select(ReleasePackage).where(ReleasePackage.organization_id==org.id).order_by(ReleasePackage.created_at.desc()).limit(1));holds=db.scalar(select(func.count(LegalHold.id)).where(LegalHold.organization_id==org.id,LegalHold.status=='Active')) or 0;return {'security_controls':{'total':len(controls),'pass':sum(x.status in {'Pass','Waived'} for x in controls),'fail':sum(x.status=='Fail' for x in controls),'pending':sum(x.status=='Pending' for x in controls)},'latest_release':ReleaseRead.model_validate(latest) if latest else None,'active_legal_holds':holds,'guardrail':'No automatic release approval or destructive purge.'}
