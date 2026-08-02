from datetime import date
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import Finding, MeasurableElement, RiskAssessmentItem, AiGovernancePolicy, PortfolioSiteMetric
HEADERS={"Authorization":"Bearer dev:test:SystemAdmin,AccreditationLead,MedicationSafety,PharmacyDirector"}

def test_risk_run_has_266_items_and_surfaces_esr_p0(client):
    with SessionLocal() as db:
        me=db.scalar(select(MeasurableElement).where(MeasurableElement.me_id=="MM.5.1"))
        db.add(Finding(site_id=db.execute(select(__import__('app.models.entities',fromlist=['Site']).Site.id)).scalar_one(),measurable_element_id=me.id,source_type="Test",criterion="Risk test",severity="P0",problem_statement="Open critical risk",owner_role_code="MedicationSafety",due_date=date.today(),status="Open"));db.commit()
    r=client.post('/api/v1/intelligence/risk-runs',headers=HEADERS,json={'code':'RISK-2026-Q3','period_label':'2026-Q3'})
    assert r.status_code==201,r.text
    assert r.json()['summary_json']['total_me']==266
    items=client.get(f"/api/v1/intelligence/risk-runs/{r.json()['id']}/items",headers=HEADERS).json()
    assert len(items)==266
    target=next(x for x in items if x['me_id']=='MM.5.1')
    assert target['risk_band']=='Critical' and target['risk_score']>=75

def test_ai_recommendations_are_human_governed(client):
    pol=client.post('/api/v1/intelligence/ai-policy/bootstrap',headers=HEADERS)
    assert pol.status_code==200
    prohibited=set(pol.json()['policy']['prohibited_actions'])
    assert {'ApproveCompliance','ApproveNotApplicable','SignEvidence','CloseCriticalCAPA','ChangeKPI'}.issubset(prohibited)
    run=client.post('/api/v1/intelligence/risk-runs',headers=HEADERS,json={'code':'RISK-AI','period_label':'AI-Q3'}).json()
    gen=client.post(f"/api/v1/intelligence/risk-runs/{run['id']}/recommendations/generate",headers=HEADERS,json={'limit':3})
    assert gen.status_code==200 and gen.json()['created']==3
    rec=gen.json()['recommendations'][0]
    assert rec['status']=='NeedsHumanReview' and rec['guardrail_result']['auto_execute'] is False
    reviewed=client.post(f"/api/v1/intelligence/recommendations/{rec['id']}/review",headers=HEADERS,json={'decision':'ApprovedForPlanning','comment':'Human reviewer accepts this only as planning input.'})
    assert reviewed.status_code==200 and reviewed.json()['status']=='HumanApprovedForPlanning'

def test_portfolio_snapshot_contains_active_site(client):
    run=client.post('/api/v1/intelligence/risk-runs',headers=HEADERS,json={'code':'RISK-PORT','period_label':'PORT'})
    assert run.status_code==201
    snap=client.post('/api/v1/intelligence/portfolio-snapshots',headers=HEADERS,json={'code':'PORT-2026-Q3','period_label':'2026-Q3'})
    assert snap.status_code==201
    detail=client.get(f"/api/v1/intelligence/portfolio-snapshots/{snap.json()['id']}",headers=HEADERS).json()
    assert detail['snapshot']['summary_json']['site_total']>=1
    assert len(detail['sites'])>=1
