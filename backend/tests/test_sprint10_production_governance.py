from datetime import datetime,timezone,timedelta
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import SecurityControlAssessment
HEADERS_ADMIN={'Authorization':'Bearer dev:test:SystemAdmin'}
HEADERS_APPROVER={'Authorization':'Bearer dev:approver:PharmacyDirector,ReadOnlyAuditor'}
SHA='a'*64

def _bootstrap_and_pass(client):
    r=client.post('/api/v1/governance/security-controls/bootstrap',headers=HEADERS_ADMIN);assert r.status_code==200 and r.json()['total']==12
    for c in client.get('/api/v1/governance/security-controls',headers=HEADERS_ADMIN).json():
        u=client.patch(f"/api/v1/governance/security-controls/{c['id']}",headers=HEADERS_ADMIN,json={'status':'Pass','evidence_reference':f"ticket:{c['code']}",'details':{'verified':True}});assert u.status_code==200
    for code,entity in [('RET-AUDIT','AuditEvent'),('RET-EVIDENCE','EvidenceItem')]:
        r=client.post('/api/v1/governance/retention-policies',headers=HEADERS_ADMIN,json={'code':code,'entity_type':entity,'retention_days':3650,'legal_basis':'Approved institutional retention baseline','purge_method':'SoftDeleteThenPurge'});assert r.status_code==201,r.text

def test_release_is_blocked_until_security_and_provenance_are_complete(client):
    pkg=client.post('/api/v1/governance/releases',headers=HEADERS_ADMIN,json={'code':'RC-1.1','version':'1.1.0','release_sha':SHA}).json()
    ev=client.post(f"/api/v1/governance/releases/{pkg['id']}/evaluate",headers=HEADERS_ADMIN)
    assert ev.status_code==200 and ev.json()['ready'] is False
    approve=client.post(f"/api/v1/governance/releases/{pkg['id']}/approve",headers=HEADERS_APPROVER)
    assert approve.status_code==409

def test_complete_release_requires_human_approval_before_publish(client):
    _bootstrap_and_pass(client)
    pkg=client.post('/api/v1/governance/releases',headers=HEADERS_ADMIN,json={'code':'RC-1.1-GOOD','version':'1.1.0','release_sha':SHA}).json()
    required=['Backend','Frontend','OpenAPI','DatabaseSchema','Seed','SBOM','Manifest','TestReport']
    for i,t in enumerate(required):
        r=client.post(f"/api/v1/governance/releases/{pkg['id']}/artifacts",headers=HEADERS_ADMIN,json={'name':f'{t.lower()}.artifact','artifact_type':t,'uri':f's3://release/{t.lower()}','sha256':hex(i+1)[2:].rjust(64,'0'),'size_bytes':100+i,'signed':t in {'Backend','Frontend','SBOM','Manifest'},'signature_reference':f'sig:{t}' if t in {'Backend','Frontend','SBOM','Manifest'} else None,'immutable':True});assert r.status_code==200,r.text
    ev=client.post(f"/api/v1/governance/releases/{pkg['id']}/evaluate",headers=HEADERS_ADMIN);assert ev.json()['ready'] is True
    pre=client.post(f"/api/v1/governance/releases/{pkg['id']}/publish",headers=HEADERS_ADMIN);assert pre.status_code==409
    app=client.post(f"/api/v1/governance/releases/{pkg['id']}/approve",headers=HEADERS_APPROVER);assert app.status_code==200 and app.json()['status']=='Approved'
    pub=client.post(f"/api/v1/governance/releases/{pkg['id']}/publish",headers=HEADERS_ADMIN);assert pub.status_code==200 and pub.json()['status']=='Published'

def test_invalid_hash_is_rejected_and_artifact_is_idempotent(client):
    pkg=client.post('/api/v1/governance/releases',headers=HEADERS_ADMIN,json={'code':'HASH-TEST','version':'1.1.0','release_sha':SHA}).json()
    bad=client.post(f"/api/v1/governance/releases/{pkg['id']}/artifacts",headers=HEADERS_ADMIN,json={'name':'bad','artifact_type':'Other','uri':'s3://x/bad','sha256':'bad','size_bytes':1});assert bad.status_code==422
    body={'name':'same','artifact_type':'Other','uri':'s3://x/same','sha256':'b'*64,'size_bytes':1}
    one=client.post(f"/api/v1/governance/releases/{pkg['id']}/artifacts",headers=HEADERS_ADMIN,json=body);two=client.post(f"/api/v1/governance/releases/{pkg['id']}/artifacts",headers=HEADERS_ADMIN,json=body)
    assert one.json()['created'] is True and two.json()['created'] is False

def test_audit_export_verifies_and_legal_hold_blocks_purge_preview(client):
    now=datetime.now(timezone.utc)
    hold=client.post('/api/v1/governance/legal-holds',headers=HEADERS_ADMIN,json={'code':'HOLD-AUDIT-1','scope_type':'EntityType','scope_id':'AuditEvent','reason':'Preserve audit evidence for formal review'});assert hold.status_code==201
    preview=client.get('/api/v1/governance/purge-preview?entity_type=AuditEvent',headers=HEADERS_ADMIN);assert preview.json()['allowed'] is False and preview.json()['delete_executed'] is False
    exp=client.post('/api/v1/governance/audit-exports',headers=HEADERS_ADMIN,json={'code':'AUDIT-EXP-1','period_start':(now-timedelta(days=1)).isoformat(),'period_end':(now+timedelta(days=1)).isoformat()});assert exp.status_code==201,exp.text
    verify=client.post(f"/api/v1/governance/audit-exports/{exp.json()['id']}/verify",headers=HEADERS_APPROVER);assert verify.status_code==200 and verify.json()['verified'] is True
    rel=client.post(f"/api/v1/governance/legal-holds/{hold.json()['id']}/release",headers=HEADERS_APPROVER,json={'reason':'Formal review completed'});assert rel.status_code==200
    assert client.get('/api/v1/governance/purge-preview?entity_type=AuditEvent',headers=HEADERS_ADMIN).json()['allowed'] is True
