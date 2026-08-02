from datetime import date, timedelta
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import PilotCycle, PilotGateCheck, UatScenario, EvidenceRequest
from app.services.pilot_control import GATE_CATALOG, REQUIRED_ROLE_CODES


def create_pilot(client):
    r=client.post('/api/v1/pilot-cycles',json={
        'code':'TGH-PILOT-01','name':'Turaif controlled pilot','objective':'Validate PIOS operational workflow before institutional go-live.',
        'period_start':str(date.today()),'period_end':str(date.today()+timedelta(days=30))
    })
    assert r.status_code==201,r.text
    return r.json()


def test_pilot_create_gates_and_p0_bootstrap_are_idempotent(client):
    pilot=create_pilot(client)
    detail=client.get(f"/api/v1/pilot-cycles/{pilot['id']}").json()
    assert detail['readiness']['gates']['total']==len(GATE_CATALOG)
    first=client.post(f"/api/v1/pilot-cycles/{pilot['id']}/bootstrap-p0")
    second=client.post(f"/api/v1/pilot-cycles/{pilot['id']}/bootstrap-p0")
    assert first.status_code==200 and first.json()['created']==48
    assert second.status_code==200 and second.json()['created']==0
    assert client.get(f"/api/v1/pilot-cycles/{pilot['id']}/readiness").json()['p0_request_count']==48


def test_participant_provisioning_covers_required_roles(client):
    pilot=create_pilot(client)
    for i,role in enumerate(sorted(REQUIRED_ROLE_CODES),start=1):
        r=client.post(f"/api/v1/pilot-cycles/{pilot['id']}/participants",json={
            'email':f'pilot{i}@tgh.local','display_name':f'Pilot User {i}','role_codes':[role],
            'external_subject':f'oidc-{i}','training_status':'Complete','access_test_status':'Pass'
        })
        assert r.status_code==201,r.text
    ready=client.get(f"/api/v1/pilot-cycles/{pilot['id']}/readiness").json()
    assert ready['participants']['missing_roles']==[] and ready['participants']['participant_count']==8


def test_go_decision_blocked_then_passes_after_gates_and_uat(client):
    pilot=create_pilot(client); pid=pilot['id']
    client.post(f'/api/v1/pilot-cycles/{pid}/bootstrap-p0')
    for i,role in enumerate(sorted(REQUIRED_ROLE_CODES),start=1):
        client.post(f'/api/v1/pilot-cycles/{pid}/participants',json={'email':f'u{i}@tgh.local','display_name':f'U{i}','role_codes':[role],'training_status':'Complete','access_test_status':'Pass'})
    blocked=client.post(f'/api/v1/pilot-cycles/{pid}/decisions',json={'decision':'Go','rationale':'Attempt go before required gates are passed.'})
    assert blocked.status_code==409
    for code,required,_ in GATE_CATALOG:
        if code!='UAT_CRITICAL_PASS':
            r=client.patch(f'/api/v1/pilot-cycles/{pid}/gates/{code}',json={'status':'Pass','evidence_reference':f'test:{code}'})
            assert r.status_code==200
    scenarios=client.get('/api/v1/uat-scenarios').json(); assert len(scenarios)==12
    for s in scenarios:
        r=client.post(f'/api/v1/pilot-cycles/{pid}/uat-executions',json={'scenario_code':s['code'],'status':'Pass','actual_result':'Expected result observed','evidence_reference':'uat-log'})
        assert r.status_code==201,r.text
    ready=client.get(f'/api/v1/pilot-cycles/{pid}/readiness').json()
    assert ready['go_live_ready'] is True and ready['uat']['pass_rate']==100.0
    decision=client.post(f'/api/v1/pilot-cycles/{pid}/decisions',json={'decision':'Go','rationale':'All required pilot gates and UAT scenarios passed.'})
    assert decision.status_code==201


def test_lifecycle_requires_readiness_and_supports_completion(client):
    pilot=create_pilot(client); pid=pilot['id']
    assert client.post(f'/api/v1/pilot-cycles/{pid}/lifecycle',json={'to_status':'ReadinessReview'}).status_code==409
    client.post(f'/api/v1/pilot-cycles/{pid}/bootstrap-p0')
    for i,role in enumerate(sorted(REQUIRED_ROLE_CODES),start=1):
        client.post(f'/api/v1/pilot-cycles/{pid}/participants',json={'email':f'l{i}@tgh.local','display_name':f'L{i}','role_codes':[role],'training_status':'Complete','access_test_status':'Pass'})
    assert client.post(f'/api/v1/pilot-cycles/{pid}/lifecycle',json={'to_status':'ReadinessReview'}).status_code==200
    for code,_,_ in GATE_CATALOG:
        if code!='UAT_CRITICAL_PASS': client.patch(f'/api/v1/pilot-cycles/{pid}/gates/{code}',json={'status':'Pass'})
    assert client.post(f'/api/v1/pilot-cycles/{pid}/lifecycle',json={'to_status':'Approved'}).status_code==200
    assert client.post(f'/api/v1/pilot-cycles/{pid}/lifecycle',json={'to_status':'Active'}).status_code==200
