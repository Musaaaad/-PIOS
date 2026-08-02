from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import (
    ServiceLevelObjective, ServiceLevelMeasurement, OperationalIncident,
    IncidentTimelineEntry, CutoverRun, CutoverTask, BaselineRelease,
    DeploymentEnvironment, DeploymentAcceptanceRun, PilotDecision, ReadinessSnapshot,
    ReadinessSnapshotItem, MeasurableElement,
)


DEFAULT_SLOS = [
    ("API_AVAILABILITY", "API availability", "Platform", "Availability", ">=", 99.5, "%", 60, "P0", "SystemAdmin"),
    ("API_P95_LATENCY", "API p95 latency", "Platform", "Latency", "<=", 750.0, "ms", 15, "P1", "SystemAdmin"),
    ("EVIDENCE_UPLOAD_SUCCESS", "Evidence upload success", "Evidence", "JobSuccess", ">=", 99.0, "%", 60, "P1", "SystemAdmin"),
    ("NOTIFICATION_JOB_SUCCESS", "Notification refresh success", "Operations", "JobSuccess", ">=", 99.0, "%", 1440, "P2", "SystemAdmin"),
    ("EXPORT_INTEGRITY", "Export checksum integrity", "Operations", "Integrity", ">=", 100.0, "%", 1440, "P1", "ReadOnlyAuditor"),
    ("BACKUP_FRESHNESS", "Backup freshness", "Resilience", "Freshness", "<=", 24.0, "hours", 1440, "P0", "SystemAdmin"),
]


CUTOVER_CATALOG = [
    ("C01", "PreGo", 10, "Freeze approved release SHA", True, "SystemAdmin", -180),
    ("C02", "PreGo", 20, "Confirm 24/24 deployment checks passed", True, "AccreditationLead", -150),
    ("C03", "PreGo", 30, "Confirm private object storage and restore evidence", True, "SystemAdmin", -120),
    ("C04", "PreGo", 40, "Confirm OIDC claims and TGH site scope", True, "SystemAdmin", -90),
    ("C05", "PreGo", 50, "Confirm support rota and rollback authority", True, "PharmacyDirector", -60),
    ("C06", "Freeze", 60, "Announce change freeze and maintenance window", True, "PharmacyDirector", -30),
    ("C07", "Deploy", 70, "Create final database and object backup", True, "SystemAdmin", -15),
    ("C08", "Deploy", 80, "Apply migration 0007", True, "SystemAdmin", 0),
    ("C09", "Deploy", 90, "Deploy backend release 1.1.0", True, "SystemAdmin", 10),
    ("C10", "Deploy", 100, "Deploy frontend release 0.4.0", True, "SystemAdmin", 20),
    ("C11", "Validate", 110, "Run health, ready and schema probes", True, "SystemAdmin", 30),
    ("C12", "Validate", 120, "Validate OIDC positive and negative tests", True, "SystemAdmin", 40),
    ("C13", "Validate", 130, "Validate evidence upload and private retrieval", True, "EvidenceReviewer", 50),
    ("C14", "Validate", 140, "Validate notification and export integrity jobs", True, "SystemAdmin", 60),
    ("C15", "Activate", 150, "Enable Turaif pilot users", True, "AccreditationLead", 75),
    ("C16", "Activate", 160, "Open the 48-request P0/ESR campaign", True, "MedicationSafety", 90),
    ("C17", "Observe", 170, "Observe SLOs and incidents for 60 minutes", True, "SystemAdmin", 150),
    ("C18", "Observe", 180, "Confirm no open P0/P1 operational incident", True, "PharmacyDirector", 160),
    ("C19", "Close", 190, "Record formal Go/No-Go decision", True, "PharmacyDirector", 180),
    ("C20", "Close", 200, "Publish cutover report and evidence index", False, "ReadOnlyAuditor", 210),
]


INCIDENT_TRANSITIONS = {
    "Open": {"Acknowledged", "Resolved"},
    "Acknowledged": {"Mitigated", "Resolved"},
    "Mitigated": {"Resolved", "Reopened"},
    "Resolved": {"Closed", "Reopened"},
    "Closed": {"Reopened"},
    "Reopened": {"Acknowledged", "Mitigated", "Resolved"},
}


def utcnow():
    return datetime.now(timezone.utc)


def ensure_default_slos(db: Session, site_id):
    existing = {x.code for x in db.scalars(select(ServiceLevelObjective).where(ServiceLevelObjective.site_id == site_id)).all()}
    created = 0
    for code, name, category, indicator, operator, target, unit, window, severity, owner in DEFAULT_SLOS:
        if code in existing:
            continue
        db.add(ServiceLevelObjective(
            site_id=site_id, code=code, name=name, category=category,
            indicator_type=indicator, target_operator=operator, target_value=target,
            unit=unit, window_minutes=window, severity_on_breach=severity,
            owner_role_code=owner,
        ))
        created += 1
    db.flush()
    return created


def measurement_status(objective: ServiceLevelObjective, value: float) -> str:
    if objective.target_operator == ">=":
        return "Pass" if value >= objective.target_value else "Breach"
    if objective.target_operator == "<=":
        return "Pass" if value <= objective.target_value else "Breach"
    raise ValueError(f"Unsupported target operator: {objective.target_operator}")


def record_measurement(db: Session, objective: ServiceLevelObjective, payload):
    row = db.scalar(select(ServiceLevelMeasurement).where(
        ServiceLevelMeasurement.objective_id == objective.id,
        ServiceLevelMeasurement.window_start == payload.window_start,
        ServiceLevelMeasurement.window_end == payload.window_end,
    ))
    if row:
        return row
    row = ServiceLevelMeasurement(
        objective_id=objective.id, window_start=payload.window_start,
        window_end=payload.window_end, numerator=payload.numerator,
        denominator=payload.denominator, measured_value=payload.measured_value,
        status=measurement_status(objective, payload.measured_value),
        source=payload.source, evidence_reference=payload.evidence_reference,
        details=payload.details,
    )
    db.add(row); db.flush(); return row


def add_timeline(db: Session, incident: OperationalIncident, event_type: str, note: str, actor_id=None, status_from=None, status_to=None, evidence_reference=None):
    row = IncidentTimelineEntry(
        incident_id=incident.id, event_type=event_type, note=note,
        status_from=status_from, status_to=status_to,
        evidence_reference=evidence_reference, actor_user_id=actor_id,
    )
    db.add(row); db.flush(); return row


def transition_incident(db: Session, incident: OperationalIncident, payload, actor_id=None):
    current = incident.status
    if payload.to_status not in INCIDENT_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=409, detail=f"Invalid incident transition: {current} -> {payload.to_status}")
    if payload.to_status == "Closed":
        root_cause = payload.root_cause or incident.root_cause
        resolution = payload.resolution_summary or incident.resolution_summary
        if not root_cause or not resolution:
            raise HTTPException(status_code=409, detail="Closing an incident requires root_cause and resolution_summary")
        incident.root_cause = root_cause
        incident.resolution_summary = resolution
        incident.closed_at = utcnow(); incident.closed_by = actor_id
    elif payload.to_status == "Acknowledged":
        incident.acknowledged_at = utcnow()
    elif payload.to_status == "Mitigated":
        incident.mitigated_at = utcnow()
    elif payload.to_status == "Resolved":
        incident.resolved_at = utcnow()
        if payload.root_cause: incident.root_cause = payload.root_cause
        if payload.resolution_summary: incident.resolution_summary = payload.resolution_summary
    elif payload.to_status == "Reopened":
        incident.closed_at = None; incident.resolved_at = None
    incident.status = payload.to_status
    add_timeline(db, incident, "StatusChange", payload.note, actor_id, current, payload.to_status, payload.evidence_reference)
    return incident


def ensure_cutover_tasks(db: Session, run: CutoverRun):
    existing = {x.code for x in db.scalars(select(CutoverTask).where(CutoverTask.cutover_run_id == run.id)).all()}
    created = 0
    for code, phase, seq, title, critical, owner, offset in CUTOVER_CATALOG:
        if code in existing: continue
        db.add(CutoverTask(cutover_run_id=run.id, code=code, phase=phase, sequence=seq, title=title, critical=critical, owner_role_code=owner, planned_offset_min=offset))
        created += 1
    db.flush(); return created


def evaluate_cutover(db: Session, run: CutoverRun):
    ensure_cutover_tasks(db, run)
    tasks = list(db.scalars(select(CutoverTask).where(CutoverTask.cutover_run_id == run.id).order_by(CutoverTask.sequence)).all())
    critical_not_passed = [x.code for x in tasks if x.critical and x.status != "Pass"]
    failed = [x.code for x in tasks if x.status in {"Fail", "Blocked"}]
    env = run.environment_id
    latest_acceptance = db.scalar(select(DeploymentAcceptanceRun).where(DeploymentAcceptanceRun.environment_id == env).order_by(DeploymentAcceptanceRun.completed_at.desc(), DeploymentAcceptanceRun.created_at.desc()).limit(1))
    acceptance_ok = bool(latest_acceptance and latest_acceptance.outcome == "Pass")
    site_id = db.scalar(select(DeploymentEnvironment.site_id).where(DeploymentEnvironment.id == env))
    open_critical = db.scalar(select(func.count(OperationalIncident.id)).where(
        OperationalIncident.site_id == site_id,
        OperationalIncident.severity.in_(["P0", "P1"]),
        OperationalIncident.status.notin_(["Closed"]),
    )) or 0
    pilot_ok = True
    pilot_decision = None
    if run.pilot_cycle_id:
        pilot_decision = db.scalar(select(PilotDecision).where(PilotDecision.pilot_cycle_id == run.pilot_cycle_id).order_by(PilotDecision.decided_at.desc()).limit(1))
        pilot_ok = bool(pilot_decision and pilot_decision.decision in {"Go", "ConditionalGo"})
    ready = not critical_not_passed and not failed and acceptance_ok and open_critical == 0 and pilot_ok
    summary = {
        "task_total": len(tasks), "task_pass": sum(x.status == "Pass" for x in tasks),
        "critical_not_passed": critical_not_passed, "failed_or_blocked": failed,
        "deployment_acceptance_pass": acceptance_ok,
        "open_p0_p1_incidents": open_critical,
        "pilot_decision": pilot_decision.decision if pilot_decision else None,
        "pilot_decision_ok": pilot_ok,
        "go_ready": ready,
    }
    run.summary_json = summary
    return summary


def decide_cutover(db: Session, run: CutoverRun, decision: str, rationale: str, actor_id=None):
    summary = evaluate_cutover(db, run)
    if decision == "Go" and not summary["go_ready"]:
        raise HTTPException(status_code=409, detail={"message": "Cutover is not ready for Go", "blockers": summary})
    run.decision = decision; run.rationale = rationale; run.approved_by = actor_id
    if decision == "Go":
        run.status = "Ready"
    elif decision == "Rollback":
        run.status = "RolledBack"; run.rollback_triggered = True; run.actual_end = utcnow()
    else:
        run.status = "Hold"
    return run


def create_baseline(db: Session, site_id, snapshot: ReadinessSnapshot, code: str, classification: str):
    item_count = db.scalar(select(func.count(ReadinessSnapshotItem.id)).where(ReadinessSnapshotItem.snapshot_id == snapshot.id)) or 0
    if item_count != 266:
        raise HTTPException(status_code=409, detail=f"Snapshot must contain 266 items; found {item_count}")
    if classification == "EvidenceReady":
        esr_green = all((v or {}).get("status") == "Green" for v in (snapshot.esr_status or {}).values())
        if snapshot.critical_open_actions or snapshot.overall_status != "EvidenceReady" or not esr_green:
            raise HTTPException(status_code=409, detail="EvidenceReady baseline requires no critical actions, EvidenceReady status and green ESR groups")
    existing = db.scalar(select(BaselineRelease).where(BaselineRelease.site_id == site_id, BaselineRelease.code == code))
    if existing: return existing
    row = BaselineRelease(
        site_id=site_id, snapshot_id=snapshot.id, code=code,
        period_label=snapshot.period_label, classification=classification,
        readiness_score=snapshot.readiness_score, overall_status=snapshot.overall_status,
        critical_open_actions=snapshot.critical_open_actions, esr_status=snapshot.esr_status,
        details={"snapshot_item_count": item_count, "claim": "Evidence readiness baseline; not a CBAHI accreditation score"},
    )
    db.add(row); db.flush(); return row


def publish_baseline(db: Session, release: BaselineRelease, actor_id=None):
    if release.status != "Approved":
        raise HTTPException(status_code=409, detail="Baseline must be Approved before publication")
    snapshot = db.get(ReadinessSnapshot, release.snapshot_id)
    rows = db.execute(
        select(ReadinessSnapshotItem, MeasurableElement.me_id)
        .join(MeasurableElement, MeasurableElement.id == ReadinessSnapshotItem.measurable_element_id)
        .where(ReadinessSnapshotItem.snapshot_id == release.snapshot_id)
        .order_by(MeasurableElement.me_id)
    ).all()
    if len(rows) != 266:
        raise HTTPException(status_code=409, detail="Baseline release requires 266 snapshot items")
    payload = {
        "release": {
            "id": str(release.id), "code": release.code, "classification": release.classification,
            "period_label": release.period_label, "readiness_score": release.readiness_score,
            "overall_status": release.overall_status, "critical_open_actions": release.critical_open_actions,
            "esr_status": release.esr_status, "details": release.details,
        },
        "snapshot": {"id": str(snapshot.id), "captured_at": snapshot.captured_at, "calculation_version": snapshot.calculation_version},
        "items": [
            {"me_id": me_id, "applicability": item.applicability, "evidence_status": item.evidence_status,
             "open_findings": item.open_findings, "highest_severity": item.highest_severity,
             "readiness_state": item.readiness_state, "rationale": item.rationale}
            for item, me_id in rows
        ],
    }
    settings = get_settings(); root = Path(settings.baseline_release_root); root.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode()
    sha = hashlib.sha256(content).hexdigest(); path = root / f"{release.code}.json"; path.write_bytes(content)
    release.status = "Published"; release.published_by = actor_id; release.published_at = utcnow(); release.release_uri = str(path); release.release_sha256 = sha
    return release
