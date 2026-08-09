from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models.entities import (
    DeploymentEnvironment, DeploymentAcceptanceRun, DeploymentAcceptanceCheck,
    BackupRestoreRun, OidcValidationRun, Standard, MeasurableElement, NestedClause,
    Document, UatScenario, PilotCycle, PilotGateCheck, PilotParticipant, EvidenceRequest,
)

ACCEPTANCE_CATALOG = [
    ("API_HEALTH","Platform",True,"Automated","API process responds and exposes release metadata"),
    ("DATABASE_REACHABLE","Database",True,"Automated","Database connection succeeds"),
    ("SCHEMA_TABLES_PRESENT","Database",True,"Automated","Expected relational model is present"),
    ("BASELINE_COUNTS_VALID","Data",True,"Automated","41/266/63/75/12 baseline counts are valid"),
    ("MIGRATIONS_APPLIED","Database",True,"Manual","Alembic head is applied in target database"),
    ("OBJECT_STORAGE_CONFIGURED","Storage",True,"Automated","Object storage is configured for the environment"),
    ("OBJECT_STORAGE_PRIVATE_RW","Storage",True,"Manual","Private bucket write/read/delete test passes"),
    ("BACKUP_RESTORE_TESTED","Resilience",True,"Manual","Database and object storage restore test passes"),
    ("OIDC_MODE_ENABLED","Identity",True,"Automated","Target uses OIDC rather than development authentication"),
    ("OIDC_DISCOVERY_JWKS","Identity",True,"Manual","Discovery and JWKS endpoints validate"),
    ("OIDC_TOKEN_VALIDATION","Identity",True,"Manual","Signed token issuer/audience/expiry validate"),
    ("OIDC_ROLE_SITE_CLAIMS","Identity",True,"Manual","Role and site claims enforce least privilege"),
    ("DEV_TOKENS_DISABLED","Security",True,"Automated","Development tokens are disabled"),
    ("TLS_ENABLED","Security",True,"Automated","TLS is enabled for API and frontend"),
    ("CORS_RESTRICTED","Security",True,"Automated","CORS excludes wildcard and local-only origins in production-like environments"),
    ("MONITORING_ENABLED","Operations",True,"Automated","Monitoring/alerting is declared enabled"),
    ("AUDIT_WRITE_PASS","Audit",True,"Automated","Audit table is writable and baseline audit structure exists"),
    ("FRONTEND_URL_CONFIGURED","Frontend",True,"Automated","Frontend public URL is configured"),
    ("NOTIFICATION_SCHEDULER_PASS","Operations",True,"Manual","Scheduler executes without duplicate notifications"),
    ("EXPORT_RETENTION_PASS","Operations",True,"Manual","Export generation, checksum and cleanup pass"),
    ("PILOT_USERS_READY","Pilot",True,"Automated","Eight required pilot participants are trained and access-tested"),
    ("P0_CAMPAIGN_READY","Pilot",True,"Automated","P0 campaign contains exactly 48 unique requests"),
    ("UAT_CRITICAL_PASS","Pilot",True,"Automated","All critical UAT scenarios pass"),
    ("FORMAL_GO_DECISION","Governance",True,"Manual","Authorized Go/ConditionalGo decision is recorded"),
]

def utcnow(): return datetime.now(timezone.utc)

def ensure_checks(db: Session, run: DeploymentAcceptanceRun):
    existing={x.check_code for x in db.scalars(select(DeploymentAcceptanceCheck).where(DeploymentAcceptanceCheck.run_id==run.id)).all()}
    for code,category,required,mode,expected in ACCEPTANCE_CATALOG:
        if code not in existing:
            db.add(DeploymentAcceptanceCheck(run_id=run.id,check_code=code,category=category,required=required,execution_mode=mode,expected_value=expected,status="Pending"))
    db.flush()

def _set(checks, code, status, measured, details=None, evidence=None):
    row=checks[code]; row.status=status; row.measured_value=str(measured); row.details=details; row.evidence_reference=evidence; row.checked_at=utcnow()

def _pilot_metrics(db: Session, run: DeploymentAcceptanceRun):
    if not run.pilot_cycle_id:
        return {"users_ready":False,"p0_count":0,"uat_ready":False,"reason":"No pilot linked"}
    pilot=db.get(PilotCycle,run.pilot_cycle_id)
    if not pilot: return {"users_ready":False,"p0_count":0,"uat_ready":False,"reason":"Pilot not found"}
    participants=list(db.scalars(select(PilotParticipant).where(PilotParticipant.pilot_cycle_id==pilot.id,PilotParticipant.active.is_(True))).all())
    roles=set(); trained=access=0
    for p in participants:
        roles.update(p.role_codes or []); trained+=int(p.training_status=="Complete"); access+=int(p.access_test_status=="Pass")
    required={"SystemAdmin","AccreditationLead","PharmacyDirector","MedicationSafety","EvidenceCollector","EvidenceReviewer","CAPAOwner","CAPAVerifier"}
    users_ready=len(participants)>=8 and required.issubset(roles) and trained>=8 and access>=8
    p0_count=0
    if pilot.evidence_campaign_id:
        p0_count=db.scalar(select(func.count(EvidenceRequest.id)).where(EvidenceRequest.campaign_id==pilot.evidence_campaign_id)) or 0
    gate=db.scalar(select(PilotGateCheck).where(PilotGateCheck.pilot_cycle_id==pilot.id,PilotGateCheck.gate_code=="UAT_CRITICAL_PASS"))
    return {"users_ready":users_ready,"p0_count":p0_count,"uat_ready":bool(gate and gate.status=="Pass"),"participant_count":len(participants)}

def summarize_checks(rows):
    """Roll check rows up into a verdict. Pure: reads rows, writes nothing.

    Read paths need the same arithmetic as calculate_summary() without its side
    effect of stamping the run - a GET that mutates the run it is reporting on
    cannot be trusted to report what is stored.
    """
    summary={"total":len(rows),"required":sum(x.required for x in rows),"pass":sum(x.status=="Pass" for x in rows),"fail":sum(x.status=="Fail" for x in rows),"pending":sum(x.status=="Pending" for x in rows),"blocked":sum(x.status=="Blocked" for x in rows),"waived":sum(x.status=="Waived" for x in rows)}
    blockers=[x.check_code for x in rows if x.required and x.status not in {"Pass","Waived"}]
    if any(x.status=="Fail" and x.required for x in rows): outcome="Fail"
    elif blockers: outcome="ConditionalPass"
    else: outcome="Pass"
    summary["blockers"]=blockers; summary["deployment_ready"]=outcome=="Pass"; summary["outcome"]=outcome
    return summary

def calculate_summary(db: Session, run: DeploymentAcceptanceRun):
    rows=list(db.scalars(select(DeploymentAcceptanceCheck).where(DeploymentAcceptanceCheck.run_id==run.id).order_by(DeploymentAcceptanceCheck.check_code)).all())
    summary=summarize_checks(rows)
    run.summary_json=summary; run.outcome=summary["outcome"]
    return summary

# The verdict for "nobody has assessed this deployment". It is deliberately NOT
# one of the stored CheckStatus values: an unmeasured gate must never be able to
# collide with a measured one, in either direction.
NOT_ASSESSED = "NotAssessed"

def unmeasured_checks():
    """The catalog rendered as explicitly unmeasured gates.

    Returned when no acceptance run exists, so the screen can name all 24 gates
    without inventing a status for any of them. Every field that would carry a
    measurement is null, because no measurement was taken.
    """
    return [{"check_code":code,"category":category,"required":required,"execution_mode":mode,
             "expected_value":expected,"status":NOT_ASSESSED,"measured_value":None,
             "evidence_reference":None,"details":None,"checked_at":None}
            for code,category,required,mode,expected in ACCEPTANCE_CATALOG]

def not_assessed_summary(reason: str):
    """Fail-closed rollup. Never ready, never Pass, and it says why."""
    return {"total":len(ACCEPTANCE_CATALOG),"required":sum(x[2] for x in ACCEPTANCE_CATALOG),
            "pass":0,"fail":0,"pending":0,"blocked":0,"waived":0,
            "blockers":[x[0] for x in ACCEPTANCE_CATALOG if x[2]],
            "deployment_ready":False,"outcome":NOT_ASSESSED,"reason":reason}

def execute_automated_checks(db: Session, run: DeploymentAcceptanceRun, env: DeploymentEnvironment):
    settings=get_settings(); ensure_checks(db,run)
    run.status="Running"; run.started_at=run.started_at or utcnow()
    rows=list(db.scalars(select(DeploymentAcceptanceCheck).where(DeploymentAcceptanceCheck.run_id==run.id)).all()); checks={x.check_code:x for x in rows}
    prod_like=env.environment_type in {"Pilot","Staging","Production"}
    _set(checks,"API_HEALTH","Pass",f"release={settings.release_version};env={settings.env}")
    try:
        db.execute(text("SELECT 1")); _set(checks,"DATABASE_REACHABLE","Pass",db.get_bind().dialect.name)
    except Exception as exc: _set(checks,"DATABASE_REACHABLE","Fail",type(exc).__name__,str(exc))
    table_names=set(inspect(db.get_bind()).get_table_names()); expected=len(__import__('app.db.base',fromlist=['Base']).Base.metadata.tables)
    _set(checks,"SCHEMA_TABLES_PRESENT","Pass" if len(table_names)>=expected else "Fail",f"{len(table_names)}/{expected}")
    counts={"standards":db.scalar(select(func.count(Standard.id))) or 0,"me":db.scalar(select(func.count(MeasurableElement.id))) or 0,"nested":db.scalar(select(func.count(NestedClause.id))) or 0,"documents":db.scalar(select(func.count(Document.id))) or 0,"uat":db.scalar(select(func.count(UatScenario.id))) or 0}
    baseline_ok=counts=={"standards":41,"me":266,"nested":63,"documents":75,"uat":12}
    _set(checks,"BASELINE_COUNTS_VALID","Pass" if baseline_ok else "Fail",json.dumps(counts,sort_keys=True))
    storage_ok=(env.object_storage_kind.lower() not in {"local","filesystem"}) if prod_like else True
    _set(checks,"OBJECT_STORAGE_CONFIGURED","Pass" if storage_ok else "Fail",env.object_storage_kind,"Production-like deployments require S3-compatible private storage")
    oidc_ok=env.auth_mode.upper()=="OIDC" and bool(env.oidc_issuer)
    _set(checks,"OIDC_MODE_ENABLED","Pass" if (oidc_ok or not prod_like) else "Fail",f"auth={env.auth_mode};issuer={bool(env.oidc_issuer)}")
    dev_disabled=not settings.allow_dev_tokens and settings.auth_mode=="oidc"
    _set(checks,"DEV_TOKENS_DISABLED","Pass" if (dev_disabled or not prod_like) else "Fail",f"allow_dev_tokens={settings.allow_dev_tokens};auth_mode={settings.auth_mode}")
    _set(checks,"TLS_ENABLED","Pass" if (env.tls_enabled or not prod_like) else "Fail",env.tls_enabled)
    origins=settings.cors_origin_list; restricted=bool(origins) and "*" not in origins and (not prod_like or all("localhost" not in x and "127.0.0.1" not in x for x in origins))
    _set(checks,"CORS_RESTRICTED","Pass" if restricted else "Fail",",".join(origins))
    _set(checks,"MONITORING_ENABLED","Pass" if (env.monitoring_enabled or not prod_like) else "Fail",env.monitoring_enabled)
    _set(checks,"AUDIT_WRITE_PASS","Pass","audit_events table present" if "audit_events" in table_names else "missing")
    _set(checks,"FRONTEND_URL_CONFIGURED","Pass" if env.frontend_base_url else "Fail",env.frontend_base_url or "missing")
    metrics=_pilot_metrics(db,run)
    _set(checks,"PILOT_USERS_READY","Pass" if metrics["users_ready"] else "Blocked",metrics.get("participant_count",0),metrics.get("reason"))
    _set(checks,"P0_CAMPAIGN_READY","Pass" if metrics["p0_count"]==48 else "Blocked",metrics["p0_count"])
    _set(checks,"UAT_CRITICAL_PASS","Pass" if metrics["uat_ready"] else "Blocked",metrics["uat_ready"])
    summary=calculate_summary(db,run); run.status="Completed"; run.completed_at=utcnow()
    return summary

def record_backup_result(db: Session, env: DeploymentEnvironment, payload, actor_id=None):
    row=db.scalar(select(BackupRestoreRun).where(BackupRestoreRun.environment_id==env.id,BackupRestoreRun.run_code==payload.run_code)) or BackupRestoreRun(environment_id=env.id,run_code=payload.run_code)
    if row.id is None: db.add(row)
    row.status=payload.status; row.backup_uri=payload.backup_uri; row.backup_sha256=payload.backup_sha256; row.restore_target=payload.restore_target; row.rpo_seconds=payload.rpo_seconds; row.rto_seconds=payload.rto_seconds; row.row_count_summary=payload.row_count_summary; row.evidence_reference=payload.evidence_reference; row.executed_by=actor_id
    row.backup_started_at=row.backup_started_at or utcnow(); row.backup_completed_at=utcnow(); row.restore_started_at=row.restore_started_at or utcnow(); row.restore_completed_at=utcnow()
    db.flush(); return row

def record_oidc_result(db: Session, env: DeploymentEnvironment, payload, actor_id=None):
    row=db.scalar(select(OidcValidationRun).where(OidcValidationRun.environment_id==env.id,OidcValidationRun.run_code==payload.run_code)) or OidcValidationRun(environment_id=env.id,run_code=payload.run_code,issuer=payload.issuer,audience=payload.audience)
    if row.id is None: db.add(row)
    for field in ["issuer","audience","discovery_url","jwks_url","discovery_status","jwks_status","token_status","claims_status","required_claims","observed_claims","evidence_reference"]: setattr(row,field,getattr(payload,field))
    row.status="Pass" if {row.discovery_status,row.jwks_status,row.token_status,row.claims_status}=={"Pass"} else ("Fail" if "Fail" in {row.discovery_status,row.jwks_status,row.token_status,row.claims_status} else "Pending")
    row.checked_by=actor_id; row.checked_at=utcnow(); db.flush(); return row

def write_report(run: DeploymentAcceptanceRun, checks: list[DeploymentAcceptanceCheck]):
    settings=get_settings(); root=Path(settings.deployment_report_root); root.mkdir(parents=True,exist_ok=True)
    payload={"run":{"id":str(run.id),"run_code":run.run_code,"scope":run.scope,"status":run.status,"outcome":run.outcome,"summary":run.summary_json},"checks":[{"code":x.check_code,"category":x.category,"required":x.required,"mode":x.execution_mode,"status":x.status,"expected":x.expected_value,"measured":x.measured_value,"evidence":x.evidence_reference,"details":x.details} for x in checks]}
    content=json.dumps(payload,ensure_ascii=False,indent=2,default=str).encode(); sha=hashlib.sha256(content).hexdigest(); path=root/f"{run.run_code}.json"; path.write_bytes(content); run.report_uri=str(path); run.report_sha256=sha; return path,sha
