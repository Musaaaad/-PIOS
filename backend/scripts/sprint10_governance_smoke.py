import json,os,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from datetime import datetime,timezone,timedelta
os.environ.setdefault('PIOS_ENV','test');os.environ.setdefault('PIOS_DATABASE_URL','sqlite+pysqlite:///:memory:');os.environ.setdefault('PIOS_ALLOW_DEV_TOKENS','true');os.environ.setdefault('PIOS_GOVERNANCE_EXPORT_ROOT',str(Path(tempfile.mkdtemp())/'exports'))
from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import engine,SessionLocal
from app.main import app
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline
Base.metadata.create_all(engine)
with SessionLocal() as db:seed_baseline(db,BaselinePayload.model_validate(json.loads((ROOT/'seeds/PIOS_MVP_Import_Data_v1.json').read_text(encoding='utf-8'))))
c=TestClient(app);A={'Authorization':'Bearer dev:test:SystemAdmin'};P={'Authorization':'Bearer dev:approver:PharmacyDirector,ReadOnlyAuditor'}
boot=c.post('/api/v1/governance/security-controls/bootstrap',headers=A).json()
for x in c.get('/api/v1/governance/security-controls',headers=A).json():c.patch(f"/api/v1/governance/security-controls/{x['id']}",headers=A,json={'status':'Pass','evidence_reference':f"smoke:{x['code']}",'details':{}})
for code,entity in [('RET-AUDIT','AuditEvent'),('RET-EVIDENCE','EvidenceItem')]:c.post('/api/v1/governance/retention-policies',headers=A,json={'code':code,'entity_type':entity,'retention_days':3650,'legal_basis':'Smoke baseline','purge_method':'SoftDeleteThenPurge'})
pkg=c.post('/api/v1/governance/releases',headers=A,json={'code':'SPRINT10-RC','version':'1.1.0','release_sha':'a'*64}).json()
for i,t in enumerate(['Backend','Frontend','OpenAPI','DatabaseSchema','Seed','SBOM','Manifest','TestReport']):c.post(f"/api/v1/governance/releases/{pkg['id']}/artifacts",headers=A,json={'name':t.lower(),'artifact_type':t,'uri':f's3://smoke/{t}','sha256':hex(i+1)[2:].rjust(64,'0'),'size_bytes':100,'signed':t in {'Backend','Frontend','SBOM','Manifest'},'signature_reference':'smoke-signature' if t in {'Backend','Frontend','SBOM','Manifest'} else None,'immutable':True})
evalr=c.post(f"/api/v1/governance/releases/{pkg['id']}/evaluate",headers=A).json();approved=c.post(f"/api/v1/governance/releases/{pkg['id']}/approve",headers=P).json();published=c.post(f"/api/v1/governance/releases/{pkg['id']}/publish",headers=A).json()
now=datetime.now(timezone.utc);exp=c.post('/api/v1/governance/audit-exports',headers=A,json={'code':'SPRINT10-AUDIT','period_start':(now-timedelta(days=1)).isoformat(),'period_end':(now+timedelta(days=1)).isoformat()}).json();verified=c.post(f"/api/v1/governance/audit-exports/{exp['id']}/verify",headers=P).json()
report={'security_controls':boot['total'],'release_ready':evalr['ready'],'release_status':published['status'],'artifact_total':evalr['artifact_total'],'audit_export_events':exp['event_count'],'audit_export_verified':verified['verified'],'warning':'Local SQLite smoke data only; not institutional production acceptance.'}
out=ROOT/'reports/sprint10_governance_smoke.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
