import json, os, sys
from datetime import date
from pathlib import Path
from sqlalchemy import select

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
os.environ.setdefault('PIOS_ENV','test')
os.environ.setdefault('PIOS_DATABASE_URL','sqlite+pysqlite:///./var/sprint9-smoke.db')
os.environ.setdefault('PIOS_ALLOW_DEV_TOKENS','true')

from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.main import app
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline
from app.models.entities import Finding, MeasurableElement, Site, RiskAssessmentItem, AiRecommendation, PortfolioSiteMetric

Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
payload=BaselinePayload.model_validate(json.loads((ROOT/'seeds/PIOS_MVP_Import_Data_v1.json').read_text(encoding='utf-8')))
with SessionLocal() as db:
    seed_baseline(db,payload)
    site=db.scalar(select(Site).where(Site.code=='TGH'))
    me=db.scalar(select(MeasurableElement).where(MeasurableElement.me_id=='MM.41.8'))
    db.add(Finding(site_id=site.id,measurable_element_id=me.id,source_type='Smoke',criterion='RCA effectiveness',severity='P0',problem_statement='Critical RCA effectiveness evidence is missing.',owner_role_code='MedicationSafety',due_date=date.today(),status='Open'))
    db.commit()

h={'Authorization':'Bearer dev:smoke:SystemAdmin,AccreditationLead,MedicationSafety,PharmacyDirector'}
c=TestClient(app)
policy=c.post('/api/v1/intelligence/ai-policy/bootstrap',headers=h).json()
risk=c.post('/api/v1/intelligence/risk-runs',headers=h,json={'code':'SPRINT9-RISK','period_label':'2026-Q3'}).json()
items=c.get(f"/api/v1/intelligence/risk-runs/{risk['id']}/items",headers=h).json()
recs=c.post(f"/api/v1/intelligence/risk-runs/{risk['id']}/recommendations/generate",headers=h,json={'limit':5}).json()
first=recs['recommendations'][0]
reviewed=c.post(f"/api/v1/intelligence/recommendations/{first['id']}/review",headers=h,json={'decision':'ApprovedForPlanning','comment':'Human review accepted this recommendation only as planning input.'}).json()
portfolio=c.post('/api/v1/intelligence/portfolio-snapshots',headers=h,json={'code':'SPRINT9-PORTFOLIO','period_label':'2026-Q3'}).json()
portfolio_detail=c.get(f"/api/v1/intelligence/portfolio-snapshots/{portfolio['id']}",headers=h).json()
report={
  'scope':'local-build-verification-only',
  'institutional_readiness':False,
  'risk_items':len(items),
  'risk_summary':risk['summary_json'],
  'top_item':{'me_id':items[0]['me_id'],'risk_score':items[0]['risk_score'],'risk_band':items[0]['risk_band']},
  'ai_policy':{'code':policy['policy']['code'],'human_review_required':policy['policy']['human_review_required'],'prohibited_actions':policy['policy']['prohibited_actions']},
  'recommendations_created':recs['created'],
  'reviewed_status':reviewed['status'],
  'portfolio_sites':portfolio_detail['snapshot']['summary_json']['site_total'],
  'safety_note':'AI recommendations are non-executing planning suggestions; risk is not a compliance score or clinical prediction.'
}
(ROOT/'reports/sprint9_intelligence_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
