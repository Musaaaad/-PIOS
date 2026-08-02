from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import hashlib,json
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models.entities import ReleasePackage,ReleaseArtifact,SecurityControlAssessment,RetentionPolicy,LegalHold,AuditExportPackage,AuditEvent

REQUIRED_ARTIFACT_TYPES={'Backend','Frontend','OpenAPI','DatabaseSchema','Seed','SBOM','Manifest','TestReport'}
SECURITY_CONTROLS=[
('SEC-IDENTITY-001','OIDC issuer, audience, JWKS and claims','Identity','P0'),
('SEC-ACCESS-001','Least privilege roles and site scope','Access','P0'),
('SEC-SECRETS-001','No secrets in source or artifacts','Secrets','P0'),
('SEC-TLS-001','TLS and approved CORS origins','Transport','P0'),
('SEC-STORAGE-001','Private encrypted object storage','Storage','P0'),
('SEC-DATABASE-001','Database encryption, backup and restore','Database','P0'),
('SEC-AUDIT-001','Append-only auditable security events','Audit','P1'),
('SEC-SBOM-001','SBOM generated and attached to release','SupplyChain','P1'),
('SEC-SCAN-001','Dependency and image scan evidence','SupplyChain','P1'),
('SEC-RETENTION-001','Approved retention and legal-hold rules','Privacy','P1'),
('SEC-EXPORT-001','Audit export integrity verification','Audit','P1'),
('SEC-MONITOR-001','Security monitoring and alert routing','Monitoring','P1'),]

def utcnow(): return datetime.now(timezone.utc)

def bootstrap_controls(db:Session,organization_id,actor_id=None):
    created=[]
    for code,title,cat,sev in SECURITY_CONTROLS:
        row=db.scalar(select(SecurityControlAssessment).where(SecurityControlAssessment.organization_id==organization_id,SecurityControlAssessment.code==code))
        if not row:
            row=SecurityControlAssessment(organization_id=organization_id,code=code,title=title,category=cat,severity=sev,required=True,status='Pending',details={'source':'PIOS Sprint 10 production governance baseline'})
            db.add(row);created.append(row)
    db.flush();return created

def create_release(db:Session,organization_id,code,version,release_sha,actor_id=None):
    existing=db.scalar(select(ReleasePackage).where(ReleasePackage.organization_id==organization_id,ReleasePackage.code==code))
    if existing:return existing
    row=ReleasePackage(organization_id=organization_id,code=code,version=version,release_sha=release_sha,status='Draft',created_by=actor_id,evaluation_json={})
    db.add(row);db.flush();return row

def add_artifact(db:Session,pkg:ReleasePackage,payload):
    if pkg.status not in {'Draft','Verified'}:raise HTTPException(409,'Artifacts cannot be changed after approval')
    existing=db.scalar(select(ReleaseArtifact).where(ReleaseArtifact.release_package_id==pkg.id,ReleaseArtifact.name==payload.name))
    if existing:
        if existing.sha256!=payload.sha256:raise HTTPException(409,'Artifact name already exists with a different hash')
        return existing,False
    row=ReleaseArtifact(release_package_id=pkg.id,**payload.model_dump())
    db.add(row);db.flush();pkg.artifact_count=db.scalar(select(func.count(ReleaseArtifact.id)).where(ReleaseArtifact.release_package_id==pkg.id)) or 0
    return row,True

def evaluate_release(db:Session,pkg:ReleasePackage):
    arts=list(db.scalars(select(ReleaseArtifact).where(ReleaseArtifact.release_package_id==pkg.id)).all())
    types={a.artifact_type for a in arts}
    missing=sorted(REQUIRED_ARTIFACT_TYPES-types)
    bad_hash=[a.name for a in arts if len(a.sha256)!=64]
    mutable=[a.name for a in arts if not a.immutable]
    unsigned=[a.name for a in arts if a.artifact_type in {'Backend','Frontend','SBOM','Manifest'} and not a.signed]
    controls=list(db.scalars(select(SecurityControlAssessment).where(SecurityControlAssessment.organization_id==pkg.organization_id,SecurityControlAssessment.required.is_(True))).all())
    control_blockers=[c.code for c in controls if c.status not in {'Pass','Waived'}]
    policies=list(db.scalars(select(RetentionPolicy).where(RetentionPolicy.organization_id==pkg.organization_id,RetentionPolicy.active.is_(True))).all())
    required_policies={'AuditEvent','EvidenceItem'}
    policy_types={p.entity_type for p in policies}
    missing_policies=sorted(required_policies-policy_types)
    ready=not any([missing,bad_hash,mutable,unsigned,control_blockers,missing_policies])
    result={'ready':ready,'artifact_total':len(arts),'artifact_types':sorted(types),'missing_artifact_types':missing,'bad_hashes':bad_hash,'mutable_artifacts':mutable,'unsigned_required_artifacts':unsigned,'security_control_blockers':control_blockers,'missing_retention_policies':missing_policies,'rule':'Human approval is mandatory; evaluation never publishes automatically.'}
    pkg.evaluation_json=result;pkg.status='Verified' if ready else 'Draft';pkg.artifact_count=len(arts);db.flush();return result

def approve_release(db:Session,pkg:ReleasePackage,actor_id=None):
    result=evaluate_release(db,pkg)
    if not result['ready']:raise HTTPException(409,detail={'message':'Release is not ready','evaluation':result})
    pkg.status='Approved';pkg.approved_by=actor_id;pkg.approved_at=utcnow();db.flush();return pkg

def publish_release(pkg:ReleasePackage,actor_id=None):
    if pkg.status!='Approved':raise HTTPException(409,'Release must be human-approved before publication')
    pkg.status='Published';pkg.published_at=utcnow();return pkg

def place_hold(db:Session,organization_id,payload,actor_id=None):
    row=LegalHold(organization_id=organization_id,placed_by=actor_id,**payload.model_dump())
    db.add(row);db.flush();return row

def release_hold(row:LegalHold,reason,actor_id=None):
    if row.status!='Active':raise HTTPException(409,'Legal hold is not active')
    row.status='Released';row.released_by=actor_id;row.released_at=utcnow();row.release_reason=reason;return row

def purge_preview(db:Session,organization_id,entity_type):
    holds=list(db.scalars(select(LegalHold).where(LegalHold.organization_id==organization_id,LegalHold.status=='Active')).all())
    blockers=[h.code for h in holds if h.scope_type in {'Organization','EntityType'} and (h.scope_type=='Organization' or h.scope_id==entity_type)]
    return {'entity_type':entity_type,'allowed':not blockers,'blocking_legal_holds':blockers,'delete_executed':False,'rule':'Preview only; no physical delete is performed by this endpoint.'}

def _event_payload(e):
    return {'id':str(e.id),'actor_id':str(e.actor_id) if e.actor_id else None,'action':e.action,'entity_type':e.entity_type,'entity_id':e.entity_id,'before_json':e.before_json,'after_json':e.after_json,'trace_id':e.trace_id,'created_at':e.created_at.isoformat() if e.created_at else None}

def create_audit_export(db:Session,organization_id,code,start,end,actor_id=None):
    if end<=start:raise HTTPException(422,'period_end must be later than period_start')
    existing=db.scalar(select(AuditExportPackage).where(AuditExportPackage.organization_id==organization_id,AuditExportPackage.code==code))
    if existing:return existing
    events=list(db.scalars(select(AuditEvent).where(AuditEvent.organization_id==organization_id,AuditEvent.created_at>=start,AuditEvent.created_at<=end).order_by(AuditEvent.created_at,AuditEvent.id)).all())
    chain='0'*64;rows=[]
    for e in events:
        item=_event_payload(e);encoded=json.dumps(item,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode();chain=hashlib.sha256((chain+hashlib.sha256(encoded).hexdigest()).encode()).hexdigest();item['chain_hash']=chain;rows.append(item)
    manifest={'code':code,'period_start':start.isoformat(),'period_end':end.isoformat(),'event_count':len(rows),'root_hash':chain,'algorithm':'SHA-256 chained event hashes','events':rows}
    raw=json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2).encode()
    settings=get_settings();root=Path(settings.governance_export_root);root.mkdir(parents=True,exist_ok=True);path=root/f'{code}.json';path.write_bytes(raw);file_sha=hashlib.sha256(raw).hexdigest()
    row=AuditExportPackage(organization_id=organization_id,code=code,period_start=start,period_end=end,status='Generated',event_count=len(rows),root_hash=chain,file_sha256=file_sha,uri=str(path),manifest_json={k:v for k,v in manifest.items() if k!='events'},created_by=actor_id)
    db.add(row);db.flush();return row

def verify_audit_export(row:AuditExportPackage,actor_id=None):
    path=Path(row.uri)
    if not path.exists():raise HTTPException(409,'Audit export file is missing')
    raw=path.read_bytes();actual=hashlib.sha256(raw).hexdigest()
    data=json.loads(raw);ok=actual==row.file_sha256 and data.get('root_hash')==row.root_hash and data.get('event_count')==row.event_count
    row.status='Verified' if ok else 'Failed';row.verified_by=actor_id;row.verified_at=utcnow();return {'verified':ok,'status':row.status,'file_sha256':actual,'root_hash':data.get('root_hash'),'event_count':data.get('event_count')}
