from datetime import date,timedelta
from app.services.deployment_acceptance import ACCEPTANCE_CATALOG

def create_env(client,kind='Integration'):
    r=client.post('/api/v1/deployment/environments',json={'code':f'{kind.lower()}-01','name':f'{kind} environment','environment_type':kind,'api_base_url':'http://api.local','frontend_base_url':'http://frontend.local','database_kind':'PostgreSQL','object_storage_kind':'Local' if kind=='Integration' else 'S3','auth_mode':'Dev' if kind=='Integration' else 'OIDC','oidc_issuer':None if kind=='Integration' else 'https://id.example','release_version':'1.0.0','tls_enabled':kind=='Integration','monitoring_enabled':kind=='Integration'})
    assert r.status_code==201,r.text; return r.json()

def create_pilot_ready(client):
    p=client.post('/api/v1/pilot-cycles',json={'code':'TGH-DEPLOY-PILOT','name':'Deployment-linked pilot','objective':'Deployment acceptance test','period_start':str(date.today()),'period_end':str(date.today()+timedelta(days=30))}).json();pid=p['id'];client.post(f'/api/v1/pilot-cycles/{pid}/bootstrap-p0')
    roles=['SystemAdmin','AccreditationLead','PharmacyDirector','MedicationSafety','EvidenceCollector','EvidenceReviewer','CAPAOwner','CAPAVerifier']
    for i,role in enumerate(roles):client.post(f'/api/v1/pilot-cycles/{pid}/participants',json={'email':f'deploy{i}@tgh.local','display_name':f'Deploy {i}','role_codes':[role],'training_status':'Complete','access_test_status':'Pass'})
    for code in ['DATABASE_READY','OBJECT_STORAGE_READY','MIGRATIONS_APPLIED','BASELINE_VALID','BACKUP_RESTORE_TESTED','OIDC_CONFIGURED','SITE_SCOPE_TESTED','PILOT_USERS_PROVISIONED','P0_ESR_CAMPAIGN_BOOTSTRAPPED','FRONTEND_SMOKE_PASS','NOTIFICATION_JOB_PASS','EXPORT_INTEGRITY_PASS','SUPPORT_ROTA_APPROVED','ROLLBACK_APPROVED','SECURITY_ACCEPTANCE']:
        client.patch(f'/api/v1/pilot-cycles/{pid}/gates/{code}',json={'status':'Pass','evidence_reference':'test'})
    for s in client.get('/api/v1/uat-scenarios').json():client.post(f'/api/v1/pilot-cycles/{pid}/uat-executions',json={'scenario_code':s['code'],'status':'Pass','actual_result':'passed','evidence_reference':'test'})
    return pid

def test_environment_and_automated_acceptance_are_idempotent(client):
    env=create_env(client);r=client.post(f"/api/v1/deployment/environments/{env['id']}/acceptance-runs",json={'run_code':'BUILD-001','scope':'BuildVerification'});assert r.status_code==201;run=r.json()
    second=client.post(f"/api/v1/deployment/environments/{env['id']}/acceptance-runs",json={'run_code':'BUILD-001','scope':'BuildVerification'});assert second.json()['id']==run['id']
    x=client.post(f"/api/v1/deployment/acceptance-runs/{run['id']}/execute-automated");assert x.status_code==200,x.text;body=x.json();assert len(body['checks'])==len(ACCEPTANCE_CATALOG);assert body['run']['outcome'] in {'ConditionalPass','Fail'}

def test_production_like_environment_blocks_unsafe_config(client):
    env=create_env(client,'Pilot');run=client.post(f"/api/v1/deployment/environments/{env['id']}/acceptance-runs",json={'run_code':'PREGO-001','scope':'PreGoLive'}).json();body=client.post(f"/api/v1/deployment/acceptance-runs/{run['id']}/execute-automated").json();statuses={x['check_code']:x['status'] for x in body['checks']};assert statuses['DEV_TOKENS_DISABLED']=='Fail';assert body['run']['outcome']=='Fail'

def test_backup_oidc_records_and_manual_check_updates(client):
    env=create_env(client);b=client.post(f"/api/v1/deployment/environments/{env['id']}/backup-restore-runs",json={'run_code':'BR-001','status':'Pass','backup_uri':'s3://backup/1','backup_sha256':'a'*64,'restore_target':'pios-restore','rpo_seconds':60,'rto_seconds':300,'row_count_summary':{'measurable_elements':266},'evidence_reference':'ticket:BR-001'});assert b.status_code==201 and b.json()['status']=='Pass'
    o=client.post(f"/api/v1/deployment/environments/{env['id']}/oidc-validations",json={'run_code':'OIDC-001','issuer':'https://id.example','audience':'pios','discovery_status':'Pass','jwks_status':'Pass','token_status':'Pass','claims_status':'Pass','observed_claims':{'sub':'u1','roles':['SystemAdmin'],'sites':['TGH']},'evidence_reference':'ticket:OIDC-001'});assert o.status_code==201 and o.json()['status']=='Pass'

def test_linked_ready_pilot_passes_pilot_automated_checks(client):
    pid=create_pilot_ready(client);env=create_env(client);run=client.post(f"/api/v1/deployment/environments/{env['id']}/acceptance-runs",json={'run_code':'LINKED-001','scope':'PreGoLive','pilot_cycle_id':pid}).json();body=client.post(f"/api/v1/deployment/acceptance-runs/{run['id']}/execute-automated").json();statuses={x['check_code']:x['status'] for x in body['checks']};assert statuses['PILOT_USERS_READY']=='Pass';assert statuses['P0_CAMPAIGN_READY']=='Pass';assert statuses['UAT_CRITICAL_PASS']=='Pass'
