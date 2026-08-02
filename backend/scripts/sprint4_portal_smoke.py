import sys
from pathlib import Path as _Path
ROOT_PATH=_Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path: sys.path.insert(0,str(ROOT_PATH))
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.main import app
from app.models.entities import EvidenceCampaign, EvidenceRequest, Finding, MeasurableElement, Site
from app.schemas.imports import BaselinePayload
from app.services.readiness import calculate_readiness
from app.services.seed import seed_baseline

ROOT=Path(__file__).resolve().parents[1]
Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
with SessionLocal() as db:
    payload=BaselinePayload.model_validate(json.loads((ROOT/'seeds/PIOS_MVP_Import_Data_v1.json').read_text()))
    seed_baseline(db,payload)
    site=db.scalar(select(Site).where(Site.code=='TGH')); me=db.scalar(select(MeasurableElement).where(MeasurableElement.me_id=='MM.5.1'))
    camp=EvidenceCampaign(site_id=site.id,name='Pilot',period_start=date.today(),period_end=date.today(),status='Open'); db.add(camp); db.flush()
    db.add(EvidenceRequest(campaign_id=camp.id,measurable_element_id=me.id,eoc=['D'],tool_code='D',due_at=datetime.now(timezone.utc)-timedelta(days=1),status='Requested'))
    db.add(Finding(site_id=site.id,measurable_element_id=me.id,criterion='ESR',severity='P0',problem_statement='Critical test finding',status='Open'))
    db.flush(); calculate_readiness(db,site.id,'Pilot'); db.commit()
client=TestClient(app)
assert client.get('/api/v1/dashboard/overview').status_code==200
refresh=client.post('/api/v1/notifications/refresh').json()
work=client.get('/api/v1/worklists/my').json()
export=client.post('/api/v1/exports',json={'export_type':'executive_pack','file_format':'zip','filters':{}}).json()
report={'dashboard':'PASS','notification_refresh':refresh,'worklist_total':work['total'],'export_status':export['status'],'export_size':export['size_bytes']}
(ROOT/'reports/sprint4_portal_smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
