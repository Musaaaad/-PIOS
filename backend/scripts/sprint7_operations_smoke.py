from __future__ import annotations
import json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
os.environ.setdefault('PIOS_ENV','test')
os.environ.setdefault('PIOS_DATABASE_URL','sqlite+pysqlite:///./var/sprint7-smoke.db')
os.environ.setdefault('PIOS_ALLOW_DEV_TOKENS','true')
os.environ.setdefault('PIOS_BASELINE_RELEASE_ROOT','./var/baseline-releases')
from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.main import app
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline
from app.services.deployment_acceptance import ACCEPTANCE_CATALOG

Path('./var').mkdir(exist_ok=True)
Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
with SessionLocal() as db:
    seed_baseline(db, BaselinePayload.model_validate(json.loads((ROOT/'seeds/PIOS_MVP_Import_Data_v1.json').read_text())))

c=TestClient(app)
headers={'Authorization':'Bearer dev:smoke:PharmacyDirector,AccreditationLead,ReadOnlyAuditor,SystemAdmin,MedicationSafety'}
# SLO and incident
c.post('/api/v1/operations/slos/bootstrap')
slos=c.get('/api/v1/operations/slos').json(); availability=next(x for x in slos if x['code']=='API_AVAILABILITY')
now=datetime.now(timezone.utc)
measurement=c.post(f"/api/v1/operations/slos/{availability['id']}/measurements",json={'window_start':(now-timedelta(hours=1)).isoformat(),'window_end':now.isoformat(),'measured_value':98.5,'source':'sprint7-smoke','evidence_reference':'smoke:slo'}).json()
incident=c.get('/api/v1/operations/incidents?severity=P0').json()[0]
# Close incident with controlled lifecycle
for status,payload in [('Acknowledged',{}),('Mitigated',{}),('Resolved',{'root_cause':'Synthetic smoke breach','resolution_summary':'Synthetic measurement reset'}),('Closed',{'root_cause':'Synthetic smoke breach','resolution_summary':'Synthetic measurement reset'})]:
    c.post(f"/api/v1/operations/incidents/{incident['id']}/transition",json={'to_status':status,'note':f'Smoke {status}',**payload})
# Deployment acceptance pass
engine_env=c.post('/api/v1/deployment/environments',json={'code':'sprint7-smoke','name':'Sprint 7 smoke environment','environment_type':'Integration','api_base_url':'http://api.local','frontend_base_url':'http://frontend.local','database_kind':'SQLite','object_storage_kind':'Local','auth_mode':'Dev','release_version':'0.8.0','tls_enabled':True,'monitoring_enabled':True}).json()
run=c.post(f"/api/v1/deployment/environments/{engine_env['id']}/acceptance-runs",json={'run_code':'SPRINT7-ACCEPT','scope':'BuildVerification'}).json(); c.post(f"/api/v1/deployment/acceptance-runs/{run['id']}/execute-automated")
for code,*_ in ACCEPTANCE_CATALOG:
    c.patch(f"/api/v1/deployment/acceptance-runs/{run['id']}/checks/{code}",json={'status':'Pass','measured_value':'smoke','evidence_reference':'smoke'})
# Cutover pass
cut=c.post('/api/v1/operations/cutovers',json={'environment_id':engine_env['id'],'code':'SPRINT7-CUT','name':'Sprint 7 controlled cutover','planned_start':now.isoformat(),'planned_end':(now+timedelta(hours=4)).isoformat()}).json()
detail=c.get(f"/api/v1/operations/cutovers/{cut['id']}").json()
for task in detail['tasks']:
    c.patch(f"/api/v1/operations/cutovers/{cut['id']}/tasks/{task['code']}",json={'status':'Pass','evidence_reference':f"smoke:{task['code']}"})
cut_eval=c.post(f"/api/v1/operations/cutovers/{cut['id']}/evaluate").json(); decision=c.post(f"/api/v1/operations/cutovers/{cut['id']}/decision",headers=headers,json={'decision':'Go','rationale':'Synthetic smoke passes all controlled cutover conditions'}).json()
# Operational baseline publish
snap=c.post('/api/v1/readiness/snapshots/calculate',json={'period_label':'SPRINT7-SMOKE'}).json(); base=c.post('/api/v1/operations/baselines',json={'snapshot_id':snap['id'],'code':'SPRINT7-BASE','classification':'OperationalBaseline'}).json(); c.post(f"/api/v1/operations/baselines/{base['id']}/approve",headers=headers); published=c.post(f"/api/v1/operations/baselines/{base['id']}/publish",headers=headers).json()
command=c.get('/api/v1/operations/command-center').json()
report={'scope':'local-build-verification-only','institutional_go_live':False,'slo_count':len(slos),'breach_measurement_status':measurement['status'],'incident_closed':c.get('/api/v1/operations/incidents?status=Closed').json()[0]['status']=='Closed','cutover_task_count':len(detail['tasks']),'cutover_go_ready':cut_eval['go_ready'],'cutover_decision':decision['decision'],'baseline_status':published['status'],'baseline_sha256':published['release_sha256'],'command_center_operational_ready':command['operational_ready']}
(ROOT/'reports/sprint7_operations_smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
