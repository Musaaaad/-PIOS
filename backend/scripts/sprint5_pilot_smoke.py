import sys, json
from pathlib import Path
from datetime import date, timedelta
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import engine,SessionLocal
from app.main import app
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline
from app.services.pilot_control import GATE_CATALOG,REQUIRED_ROLE_CODES
Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
with SessionLocal() as db:
    seed_baseline(db,BaselinePayload.model_validate(json.loads((ROOT/'seeds/PIOS_MVP_Import_Data_v1.json').read_text())))
client=TestClient(app)
p=client.post('/api/v1/pilot-cycles',json={'code':'TGH-SMOKE','name':'TGH pilot smoke','objective':'Validate pilot control workflow and P0 campaign bootstrap.','period_start':str(date.today()),'period_end':str(date.today()+timedelta(days=30))}).json();pid=p['id']
boot=client.post(f'/api/v1/pilot-cycles/{pid}/bootstrap-p0').json()
for i,role in enumerate(sorted(REQUIRED_ROLE_CODES),1): client.post(f'/api/v1/pilot-cycles/{pid}/participants',json={'email':f'smoke{i}@tgh.local','display_name':f'Smoke {i}','role_codes':[role],'training_status':'Complete','access_test_status':'Pass'})
for code,_,_ in GATE_CATALOG:
    if code!='UAT_CRITICAL_PASS': client.patch(f'/api/v1/pilot-cycles/{pid}/gates/{code}',json={'status':'Pass','evidence_reference':'smoke'})
for s in client.get('/api/v1/uat-scenarios').json(): client.post(f'/api/v1/pilot-cycles/{pid}/uat-executions',json={'scenario_code':s['code'],'status':'Pass','actual_result':'PASS'})
ready=client.get(f'/api/v1/pilot-cycles/{pid}/readiness').json()
decision=client.post(f'/api/v1/pilot-cycles/{pid}/decisions',json={'decision':'Go','rationale':'All smoke test gates and UAT scenarios passed.'}).json()
report={'pilot_id':pid,'bootstrap':boot,'participants':ready['participants']['participant_count'],'roles_missing':ready['participants']['missing_roles'],'gates':ready['gates'],'uat_pass_rate':ready['uat']['pass_rate'],'go_live_ready':ready['go_live_ready'],'decision':decision['decision']}
(ROOT/'reports/sprint5_pilot_smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
