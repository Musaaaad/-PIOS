from __future__ import annotations
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    EvidenceCampaign, EvidenceRequest, MeasurableElement, PilotCycle, PilotParticipant,
    PilotGateCheck, UatScenario, UatExecution, PilotDecision, UserRole, Role,
    ReadinessSnapshot,
)

P0_ME_IDS = [
    "MM.3.6", "MM.5.1", "MM.5.2", "MM.5.3", "MM.5.4", "MM.6.1", "MM.6.2", "MM.6.3",
    "MM.12.7", "MM.12.8", "MM.12.10", "MM.16.6", "MM.18.4", "MM.18.5", "MM.20.3", "MM.20.8",
    "MM.23.3", "MM.23.4", "MM.25.2", "MM.25.3", "MM.25.4", "MM.31.7", "MM.32.4", "MM.33.2",
    "MM.36.2", "MM.36.3", "MM.36.5", "MM.36.7", "MM.36.8", "MM.37.1", "MM.37.2", "MM.37.7",
    "MM.38.2", "MM.39.4", "MM.40.4", "MM.40.9", "MM.41.1", "MM.41.2", "MM.41.3", "MM.41.4",
    "MM.41.5", "MM.41.6", "MM.41.7", "MM.41.8", "MM.41.9", "MM.41.10", "MM.41.11", "MM.41.12",
]

GATE_CATALOG = [
    ("DATABASE_READY", True, "PostgreSQL reachable and schema validated"),
    ("OBJECT_STORAGE_READY", True, "Evidence object storage is private and writable"),
    ("MIGRATIONS_APPLIED", True, "Alembic migrations applied through Sprint 5"),
    ("BASELINE_VALID", True, "41/266/63/75 baseline validated"),
    ("BACKUP_RESTORE_TESTED", True, "Backup and restore test completed"),
    ("OIDC_CONFIGURED", True, "OIDC issuer, audience, JWKS and claims validated"),
    ("SITE_SCOPE_TESTED", True, "TGH site scope and least privilege verified"),
    ("PILOT_USERS_PROVISIONED", True, "Required pilot roles are assigned"),
    ("P0_ESR_CAMPAIGN_BOOTSTRAPPED", True, "48 P0 requests created idempotently"),
    ("FRONTEND_SMOKE_PASS", True, "Arabic/English, RTL/LTR and core screens passed"),
    ("NOTIFICATION_JOB_PASS", True, "Notification refresh is idempotent"),
    ("EXPORT_INTEGRITY_PASS", True, "Executive export and SHA-256 verified"),
    ("UAT_CRITICAL_PASS", True, "No failed P0/P1 UAT scenario"),
    ("SUPPORT_ROTA_APPROVED", True, "Support and escalation rota approved"),
    ("ROLLBACK_APPROVED", True, "Rollback triggers and owner approved"),
    ("SECURITY_ACCEPTANCE", True, "IT security and data protection acceptance"),
]

REQUIRED_ROLE_CODES = {
    "SystemAdmin", "AccreditationLead", "PharmacyDirector", "MedicationSafety",
    "EvidenceCollector", "EvidenceReviewer", "CAPAOwner", "CAPAVerifier",
}

PILOT_TRANSITIONS = {
    "Draft": {"ReadinessReview", "RolledBack"},
    "ReadinessReview": {"Approved", "Draft", "RolledBack"},
    "Approved": {"Active", "RolledBack"},
    "Active": {"Suspended", "Completed", "RolledBack"},
    "Suspended": {"Active", "RolledBack"},
    "Completed": set(),
    "RolledBack": set(),
}


def now_utc():
    return datetime.now(timezone.utc)


def ensure_gate_rows(db: Session, pilot: PilotCycle):
    existing = {x.gate_code for x in db.scalars(select(PilotGateCheck).where(PilotGateCheck.pilot_cycle_id == pilot.id)).all()}
    for code, required, _ in GATE_CATALOG:
        if code not in existing:
            db.add(PilotGateCheck(pilot_cycle_id=pilot.id, gate_code=code, required=required, status="Pending"))
    db.flush()


def bootstrap_p0_campaign(db: Session, pilot: PilotCycle, due_at=None):
    campaign = db.get(EvidenceCampaign, pilot.evidence_campaign_id) if pilot.evidence_campaign_id else None
    if not campaign:
        campaign = EvidenceCampaign(
            site_id=pilot.site_id, name=f"{pilot.code} - P0/ESR",
            description="Controlled pilot campaign for the 48 P0 collection-pack measurable elements.",
            period_start=pilot.period_start, period_end=pilot.period_end, status="Draft",
        )
        db.add(campaign); db.flush(); pilot.evidence_campaign_id = campaign.id
    me_rows = list(db.scalars(select(MeasurableElement).where(MeasurableElement.me_id.in_(P0_ME_IDS))).all())
    found = {x.me_id for x in me_rows}
    missing = sorted(set(P0_ME_IDS)-found)
    if missing:
        raise HTTPException(status_code=409, detail={"missing_p0_me_ids": missing})
    existing = {(x.measurable_element_id, x.tool_code) for x in db.scalars(select(EvidenceRequest).where(EvidenceRequest.campaign_id == campaign.id)).all()}
    created = 0
    for me in me_rows:
        key=(me.id,"P0_PACK")
        if key in existing: continue
        db.add(EvidenceRequest(
            campaign_id=campaign.id, measurable_element_id=me.id, eoc=me.eoc,
            tool_code="P0_PACK", due_at=due_at, status="Requested",
            instructions="Collect representative evidence across applicable sites/shifts and satisfy every EOC method before review.",
        )); created += 1
    db.flush()
    gate = db.scalar(select(PilotGateCheck).where(PilotGateCheck.pilot_cycle_id==pilot.id, PilotGateCheck.gate_code=="P0_ESR_CAMPAIGN_BOOTSTRAPPED"))
    if gate:
        gate.status="Pass"; gate.evidence_reference=f"campaign:{campaign.id};requests:48"; gate.checked_at=now_utc()
    return campaign, created


def participant_role_coverage(db: Session, pilot_id):
    participants=list(db.scalars(select(PilotParticipant).where(PilotParticipant.pilot_cycle_id==pilot_id, PilotParticipant.active.is_(True))).all())
    roles=set()
    trained=0; access_pass=0
    for p in participants:
        roles.update(p.role_codes or [])
        trained += int(p.training_status=="Complete")
        access_pass += int(p.access_test_status=="Pass")
    return {"participant_count":len(participants),"role_codes":sorted(roles),"missing_roles":sorted(REQUIRED_ROLE_CODES-roles),"trained":trained,"access_pass":access_pass}


def uat_summary(db: Session, pilot_id):
    scenarios=list(db.scalars(select(UatScenario).where(UatScenario.active.is_(True)).order_by(UatScenario.code)).all())
    executions=list(db.scalars(select(UatExecution).where(UatExecution.pilot_cycle_id==pilot_id).order_by(UatExecution.created_at)).all())
    latest={}
    scenario_by_id={x.id:x for x in scenarios}
    for row in executions:
        key=row.scenario_id
        if key not in latest or row.attempt >= latest[key].attempt:
            latest[key]=row
    totals={"total":len(scenarios),"pass":0,"fail":0,"blocked":0,"not_run":0,"critical_failures":0}
    details=[]
    for s in scenarios:
        run=latest.get(s.id); status=run.status if run else "NotRun"
        if status=="Pass": totals["pass"]+=1
        elif status=="Fail": totals["fail"]+=1
        elif status=="Blocked": totals["blocked"]+=1
        else: totals["not_run"]+=1
        if s.criticality in {"P0","P1"} and status != "Pass": totals["critical_failures"] += 1
        details.append({"scenario_code":s.code,"criticality":s.criticality,"status":status,"attempt":run.attempt if run else None,"defect_severity":run.defect_severity if run else None})
    executed=totals["pass"]+totals["fail"]+totals["blocked"]
    totals["pass_rate"] = round(totals["pass"]/executed*100,1) if executed else 0.0
    totals["details"] = details
    return totals


def pilot_readiness(db: Session, pilot: PilotCycle):
    ensure_gate_rows(db,pilot)
    gates=list(db.scalars(select(PilotGateCheck).where(PilotGateCheck.pilot_cycle_id==pilot.id).order_by(PilotGateCheck.gate_code)).all())
    gate_summary={"total":len(gates),"required":sum(x.required for x in gates),"pass":sum(x.status=="Pass" for x in gates),"fail":sum(x.status=="Fail" for x in gates),"pending":sum(x.status=="Pending" for x in gates),"waived":sum(x.status=="Waived" for x in gates)}
    participants=participant_role_coverage(db,pilot.id)
    requests=0
    if pilot.evidence_campaign_id:
        requests=db.scalar(select(func.count(EvidenceRequest.id)).where(EvidenceRequest.campaign_id==pilot.evidence_campaign_id)) or 0
    uat=uat_summary(db,pilot.id)
    latest_snapshot=db.scalar(select(ReadinessSnapshot).where(ReadinessSnapshot.site_id==pilot.site_id).order_by(ReadinessSnapshot.captured_at.desc()))
    required_pass=all((not x.required) or x.status in {"Pass","Waived"} for x in gates)
    users_ready=not participants["missing_roles"] and participants["participant_count"]>=8 and participants["trained"]>=8 and participants["access_pass"]>=8
    uat_ready=uat["critical_failures"]==0 and uat["not_run"]==0 and uat["pass_rate"]>=90
    go_live_ready=required_pass and users_ready and requests==48 and uat_ready
    return {
        "pilot_id":str(pilot.id),"status":pilot.status,"gates":gate_summary,"gate_details":[{"code":x.gate_code,"required":x.required,"status":x.status,"evidence_reference":x.evidence_reference} for x in gates],
        "participants":participants,"p0_request_count":requests,"uat":uat,"go_live_ready":go_live_ready,
        "latest_readiness_snapshot":({"id":str(latest_snapshot.id),"score":latest_snapshot.readiness_score,"overall_status":latest_snapshot.overall_status,"critical_open_actions":latest_snapshot.critical_open_actions} if latest_snapshot else None),
        "blockers":[
            *( ["Required pilot gates are not all passed"] if not required_pass else [] ),
            *( ["Required pilot roles/training/access are incomplete"] if not users_ready else [] ),
            *( [f"P0 campaign request count is {requests}, expected 48"] if requests!=48 else [] ),
            *( ["Critical UAT scenarios are not all passed"] if not uat_ready else [] ),
        ],
    }


def transition_pilot(db: Session, pilot: PilotCycle, to_status: str):
    if to_status not in PILOT_TRANSITIONS.get(pilot.status,set()):
        raise HTTPException(status_code=409, detail=f"Invalid pilot transition: {pilot.status} -> {to_status}")
    readiness=pilot_readiness(db,pilot)
    if to_status=="ReadinessReview":
        if readiness["p0_request_count"]!=48 or readiness["participants"]["missing_roles"]:
            raise HTTPException(status_code=409, detail={"message":"Pilot is not ready for readiness review","blockers":readiness["blockers"]})
    if to_status=="Approved":
        pre_uat_exempt={"UAT_CRITICAL_PASS"}
        blocking=[x for x in readiness["gate_details"] if x["required"] and x["code"] not in pre_uat_exempt and x["status"] not in {"Pass","Waived"}]
        if blocking:
            raise HTTPException(status_code=409, detail={"message":"Required pre-activation gates are not passed","gates":blocking})
    if to_status=="Active" and pilot.status!="Suspended":
        if pilot.status!="Approved": raise HTTPException(status_code=409,detail="Pilot must be Approved before activation")
        pilot.activated_at=now_utc()
    if to_status=="Completed":
        latest=db.scalar(select(PilotDecision).where(PilotDecision.pilot_cycle_id==pilot.id).order_by(PilotDecision.created_at.desc()))
        if not latest or latest.decision not in {"Go","ConditionalGo"} or not readiness["go_live_ready"]:
            raise HTTPException(status_code=409, detail={"message":"Pilot cannot complete without a Go decision and all gates","blockers":readiness["blockers"]})
        pilot.completed_at=now_utc()
    pilot.status=to_status
    return readiness
