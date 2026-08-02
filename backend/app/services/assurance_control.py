from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AssuranceProgram, AssuranceControl, AssuranceCycle, AssuranceTask,
    DataQualityRule, DataQualityRun, DataQualityIssue,
    RolloutWave, RolloutWaveSite, Organization, Site, MeasurableElement,
    Finding, Capa, DocumentVersion,
)

P0_ME_IDS = [
    "MM.3.6", "MM.5.1", "MM.5.2", "MM.5.3", "MM.5.4", "MM.6.1", "MM.6.2", "MM.6.3",
    "MM.12.7", "MM.12.8", "MM.12.10", "MM.16.6", "MM.18.4", "MM.18.5", "MM.20.3", "MM.20.8",
    "MM.23.3", "MM.23.4", "MM.25.2", "MM.25.3", "MM.25.4", "MM.31.7", "MM.32.4", "MM.33.2",
    "MM.36.2", "MM.36.3", "MM.36.5", "MM.36.7", "MM.36.8", "MM.37.1", "MM.37.2", "MM.37.7",
    "MM.38.2", "MM.39.4", "MM.40.4", "MM.40.9", "MM.41.1", "MM.41.2", "MM.41.3", "MM.41.4",
    "MM.41.5", "MM.41.6", "MM.41.7", "MM.41.8", "MM.41.9", "MM.41.10", "MM.41.11", "MM.41.12",
]

DQ_RULES = [
    ("P0_CONTROL_MISSING", "P0/ESR measurable element has no active recurring control", "Assurance", "P0", "AccreditationLead"),
    ("OVERDUE_ASSURANCE_CONTROL", "Recurring assurance control is overdue", "Assurance", "P1", "MEOwner"),
    ("OVERDUE_FINDING", "Open finding is overdue", "CAPA", "P1", "CAPAOwner"),
    ("OVERDUE_CAPA", "Open CAPA is overdue", "CAPA", "P1", "CAPAOwner"),
    ("DOCUMENT_REVIEW_OVERDUE", "Effective or approved document review date is overdue", "Documents", "P2", "AccreditationLead"),
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_p0_program(db: Session, site_id, actor_id=None) -> tuple[AssuranceProgram, int]:
    program = db.scalar(select(AssuranceProgram).where(AssuranceProgram.site_id == site_id, AssuranceProgram.code == "TGH-P0-ESR"))
    if not program:
        program = AssuranceProgram(
            site_id=site_id, code="TGH-P0-ESR", name="Turaif P0 and ESR Continuous Assurance",
            scope="P0_ESR", status="Active", cadence_days=90, lookahead_days=30,
            owner_role_code="AccreditationLead", start_date=date.today(), created_by=actor_id,
        )
        db.add(program); db.flush()
    rows = list(db.scalars(select(MeasurableElement).where(MeasurableElement.me_id.in_(P0_ME_IDS))).all())
    if len(rows) != 48:
        raise HTTPException(status_code=409, detail=f"P0/ESR scope requires 48 measurable elements; found {len(rows)}")
    existing = set(db.scalars(select(AssuranceControl.measurable_element_id).where(AssuranceControl.program_id == program.id)).all())
    created = 0
    now = utcnow()
    for me in rows:
        if me.id in existing:
            continue
        cadence = 30 if me.esr else 90
        db.add(AssuranceControl(
            program_id=program.id, measurable_element_id=me.id,
            code=f"CTRL-{me.me_id.replace('.', '-')}", title=f"Recurring assurance for {me.me_id}",
            critical=True, cadence_days=cadence, evidence_types=list(me.eoc or []),
            owner_role_code=me.owner_role_code or ("MedicationSafety" if me.esr else "MEOwner"),
            active=True, next_due_at=now + timedelta(days=cadence),
        ))
        created += 1
    db.flush()
    return program, created


def open_cycle(db: Session, program: AssuranceProgram, code: str, period_label: str, due_at: datetime, actor_id=None) -> AssuranceCycle:
    existing = db.scalar(select(AssuranceCycle).where(AssuranceCycle.program_id == program.id, AssuranceCycle.code == code))
    if existing:
        return existing
    if program.status != "Active":
        raise HTTPException(status_code=409, detail="Assurance program must be Active")
    cycle = AssuranceCycle(
        program_id=program.id, code=code, period_label=period_label,
        status="Open", due_at=due_at, created_by=actor_id,
    )
    db.add(cycle); db.flush()
    controls = list(db.scalars(select(AssuranceControl).where(AssuranceControl.program_id == program.id, AssuranceControl.active.is_(True)).order_by(AssuranceControl.code)).all())
    if not controls:
        raise HTTPException(status_code=409, detail="Assurance program has no active controls")
    for control in controls:
        db.add(AssuranceTask(cycle_id=cycle.id, control_id=control.id, status="Pending", due_at=due_at))
    cycle.summary_json = {"task_total": len(controls), "task_pass": 0, "task_fail": 0, "task_pending": len(controls)}
    db.flush()
    return cycle


def complete_task(db: Session, task: AssuranceTask, result: str, evidence_reference: str | None, comment: str | None, actor_id=None) -> AssuranceTask:
    if task.status == "Completed":
        raise HTTPException(status_code=409, detail="Assurance task is already completed")
    control = db.get(AssuranceControl, task.control_id)
    if not control:
        raise HTTPException(status_code=404, detail="Assurance control not found")
    me = db.get(MeasurableElement, control.measurable_element_id)
    cycle = db.get(AssuranceCycle, task.cycle_id)
    program = db.get(AssuranceProgram, cycle.program_id) if cycle else None
    now = utcnow()
    task.status = "Completed"
    task.result = result
    task.evidence_reference = evidence_reference
    task.comment = comment
    task.completed_by = actor_id
    task.completed_at = now
    control.last_completed_at = now
    control.next_due_at = now + timedelta(days=(7 if result == "Fail" else control.cadence_days))
    if result == "Fail" and not task.finding_id:
        finding = Finding(
            site_id=program.site_id, measurable_element_id=me.id, source_type="AssuranceTask",
            criterion=f"Recurring assurance control {control.code}",
            severity="P0" if (control.critical or me.esr) else "P1",
            problem_statement=comment or f"Recurring assurance control failed for {me.me_id}",
            owner_role_code=control.owner_role_code,
            due_date=date.today() + timedelta(days=7 if (control.critical or me.esr) else 30),
            status="Open",
        )
        db.add(finding); db.flush(); task.finding_id = finding.id
    db.flush()
    return task


def close_cycle(db: Session, cycle: AssuranceCycle) -> AssuranceCycle:
    tasks = list(db.scalars(select(AssuranceTask).where(AssuranceTask.cycle_id == cycle.id)).all())
    pending = [x for x in tasks if x.status != "Completed"]
    if pending:
        raise HTTPException(status_code=409, detail=f"Cannot close cycle with {len(pending)} incomplete tasks")
    pass_count = sum(x.result == "Pass" for x in tasks)
    fail_count = sum(x.result == "Fail" for x in tasks)
    na_count = sum(x.result == "NotApplicable" for x in tasks)
    cycle.status = "ClosedWithFindings" if fail_count else "Closed"
    cycle.closed_at = utcnow()
    cycle.summary_json = {"task_total": len(tasks), "task_pass": pass_count, "task_fail": fail_count, "task_na": na_count, "task_pending": 0}
    db.flush()
    return cycle


def ensure_dq_rules(db: Session) -> int:
    existing = set(db.scalars(select(DataQualityRule.code)).all())
    created = 0
    for code, name, category, severity, owner in DQ_RULES:
        if code in existing:
            continue
        db.add(DataQualityRule(code=code, name=name, category=category, severity=severity, owner_role_code=owner, active=True, config={}))
        created += 1
    db.flush()
    return created


def execute_dq_run(db: Session, site_id, code: str, actor_id=None) -> DataQualityRun:
    existing = db.scalar(select(DataQualityRun).where(DataQualityRun.site_id == site_id, DataQualityRun.code == code))
    if existing:
        return existing
    ensure_dq_rules(db)
    rules = {x.code: x for x in db.scalars(select(DataQualityRule).where(DataQualityRule.active.is_(True))).all()}
    run = DataQualityRun(site_id=site_id, code=code, status="Running", created_by=actor_id)
    db.add(run); db.flush()
    issues: list[DataQualityIssue] = []
    now = utcnow(); today = date.today()

    p0_mes = list(db.scalars(select(MeasurableElement).where(MeasurableElement.me_id.in_(P0_ME_IDS))).all())
    active_control_me_ids = set(db.scalars(
        select(AssuranceControl.measurable_element_id).join(AssuranceProgram, AssuranceProgram.id == AssuranceControl.program_id)
        .where(AssuranceProgram.site_id == site_id, AssuranceControl.active.is_(True))
    ).all())
    for me in p0_mes:
        if me.id not in active_control_me_ids:
            rule = rules["P0_CONTROL_MISSING"]
            issues.append(DataQualityIssue(run_id=run.id, rule_id=rule.id, entity_type="MeasurableElement", entity_id=me.me_id, message=f"{me.me_id} has no active recurring assurance control", severity=rule.severity, owner_role_code=rule.owner_role_code))

    overdue_controls = db.execute(
        select(AssuranceControl, MeasurableElement.me_id)
        .join(AssuranceProgram, AssuranceProgram.id == AssuranceControl.program_id)
        .join(MeasurableElement, MeasurableElement.id == AssuranceControl.measurable_element_id)
        .where(AssuranceProgram.site_id == site_id, AssuranceControl.active.is_(True), AssuranceControl.next_due_at.is_not(None), AssuranceControl.next_due_at < now)
    ).all()
    for control, me_id in overdue_controls:
        rule = rules["OVERDUE_ASSURANCE_CONTROL"]
        issues.append(DataQualityIssue(run_id=run.id, rule_id=rule.id, entity_type="AssuranceControl", entity_id=str(control.id), message=f"{me_id} assurance control is overdue", severity="P0" if control.critical else rule.severity, owner_role_code=control.owner_role_code))

    findings = list(db.scalars(select(Finding).where(Finding.site_id == site_id, Finding.status.not_in(["Closed"]), Finding.due_date.is_not(None), Finding.due_date < today)).all())
    for row in findings:
        rule = rules["OVERDUE_FINDING"]
        issues.append(DataQualityIssue(run_id=run.id, rule_id=rule.id, entity_type="Finding", entity_id=str(row.id), message="Open finding is overdue", severity=row.severity if row.severity in {"P0","P1"} else rule.severity, owner_role_code=row.owner_role_code or rule.owner_role_code))

    capas = list(db.scalars(select(Capa).join(Finding, Finding.id == Capa.finding_id).where(Finding.site_id == site_id, Capa.status.not_in(["Closed"]), Capa.due_date.is_not(None), Capa.due_date < today)).all())
    for row in capas:
        rule = rules["OVERDUE_CAPA"]
        issues.append(DataQualityIssue(run_id=run.id, rule_id=rule.id, entity_type="Capa", entity_id=str(row.id), message="Open CAPA is overdue", severity=rule.severity, owner_role_code=row.owner_role_code or rule.owner_role_code))

    versions = list(db.scalars(select(DocumentVersion).where(DocumentVersion.status.in_(["Effective", "Approved"]), DocumentVersion.review_date.is_not(None), DocumentVersion.review_date < today)).all())
    for row in versions:
        rule = rules["DOCUMENT_REVIEW_OVERDUE"]
        issues.append(DataQualityIssue(run_id=run.id, rule_id=rule.id, entity_type="DocumentVersion", entity_id=str(row.id), message=f"Document version {row.version_label} review date is overdue", severity=rule.severity, owner_role_code=rule.owner_role_code))

    db.add_all(issues)
    counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    run.status = "Completed"
    run.completed_at = now
    run.summary_json = {"issue_total": len(issues), "by_severity": counts, "quality_pass": len(issues) == 0}
    db.flush()
    return run


def create_rollout_wave(db: Session, organization_id, template_site_id, code: str, name: str, planned_start: date, planned_end: date, owner_role_code: str, actor_id=None) -> RolloutWave:
    existing = db.scalar(select(RolloutWave).where(RolloutWave.organization_id == organization_id, RolloutWave.code == code))
    if existing:
        return existing
    row = RolloutWave(organization_id=organization_id, template_site_id=template_site_id, code=code, name=name, status="Draft", planned_start=planned_start, planned_end=planned_end, owner_role_code=owner_role_code, summary_json={}, created_by=actor_id)
    db.add(row); db.flush(); return row


def add_rollout_site(db: Session, wave: RolloutWave, site_code: str, name_ar: str, name_en: str, site_type: str) -> RolloutWaveSite:
    site = db.scalar(select(Site).where(Site.organization_id == wave.organization_id, Site.code == site_code))
    if not site:
        site = Site(organization_id=wave.organization_id, code=site_code, name_ar=name_ar, name_en=name_en, site_type=site_type, timezone="Asia/Riyadh", active=True)
        db.add(site); db.flush()
    existing = db.scalar(select(RolloutWaveSite).where(RolloutWaveSite.wave_id == wave.id, RolloutWaveSite.site_id == site.id))
    if existing:
        return existing
    row = RolloutWaveSite(wave_id=wave.id, site_id=site.id, status="Planned", gate_status={})
    db.add(row); db.flush(); return row


def update_rollout_site(row: RolloutWaveSite, *, baseline_imported: bool, users_ready: bool, training_complete: bool, deployment_pass: bool, oidc_pass: bool, evidence_reference: str | None = None) -> RolloutWaveSite:
    row.baseline_imported = baseline_imported
    row.users_ready = users_ready
    row.training_complete = training_complete
    row.deployment_pass = deployment_pass
    row.oidc_pass = oidc_pass
    row.go_live_ready = all([baseline_imported, users_ready, training_complete, deployment_pass, oidc_pass])
    row.status = "Ready" if row.go_live_ready else "InProgress"
    row.gate_status = {
        "baseline_imported": baseline_imported, "users_ready": users_ready,
        "training_complete": training_complete, "deployment_pass": deployment_pass,
        "oidc_pass": oidc_pass, "evidence_reference": evidence_reference,
    }
    return row


def update_wave_summary(db: Session, wave: RolloutWave) -> dict:
    rows = list(db.scalars(select(RolloutWaveSite).where(RolloutWaveSite.wave_id == wave.id)).all())
    summary = {"site_total": len(rows), "site_ready": sum(x.go_live_ready for x in rows), "site_blocked": sum(not x.go_live_ready for x in rows)}
    wave.summary_json = summary
    if rows and summary["site_ready"] == len(rows):
        wave.status = "Ready"
    elif rows:
        wave.status = "InProgress"
    return summary
