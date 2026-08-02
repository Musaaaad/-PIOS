import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('PIOS_ENV','test');os.environ.setdefault('PIOS_DATABASE_URL','sqlite+pysqlite:///./var/sprint6-smoke.db');os.environ.setdefault('PIOS_ALLOW_DEV_TOKENS','true')
from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import engine,SessionLocal
from app.main import app
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline
Path('./var').mkdir(exist_ok=True);Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
with SessionLocal() as db:seed_baseline(db,BaselinePayload.model_validate(json.loads((ROOT/'seeds/PIOS_MVP_Import_Data_v1.json').read_text())))
c=TestClient(app);env=c.post('/api/v1/deployment/environments',json={'code':'local-smoke','name':'Local build verification','environment_type':'Integration','api_base_url':'http://localhost:8000','frontend_base_url':'http://localhost:8080','database_kind':'SQLite','object_storage_kind':'Local','auth_mode':'Dev','release_version':'0.8.0','tls_enabled':False,'monitoring_enabled':False}).json();run=c.post(f"/api/v1/deployment/environments/{env['id']}/acceptance-runs",json={'run_code':'SPRINT6-LOCAL','scope':'BuildVerification'}).json();result=c.post(f"/api/v1/deployment/acceptance-runs/{run['id']}/execute-automated").json();report={'scope':'local-build-verification-only','institutional_go_live':False,'environment_id':env['id'],'run_id':run['id'],'outcome':result['run']['outcome'],'summary':result['run']['summary_json'],'checks':{x['check_code']:x['status'] for x in result['checks']}};(ROOT/'reports/sprint6_deployment_acceptance_smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
