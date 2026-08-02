from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import Capa, CapaAction, EffectivenessCheck, Finding, MeasurableElement

SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def active_actions(db: Session, capa_id):
    return list(db.scalars(select(CapaAction).where(CapaAction.capa_id == capa_id).order_by(CapaAction.sequence)).all())


def effectiveness_checks(db: Session, capa_id):
    return list(db.scalars(select(EffectivenessCheck).where(EffectivenessCheck.capa_id == capa_id).order_by(EffectivenessCheck.created_at)).all())


def validate_capa_submit(db: Session, capa: Capa) -> dict:
    if capa.status not in {"Draft", "Reopened"}:
        raise HTTPException(status_code=409, detail="CAPA can only be submitted from Draft or Reopened")
    if not capa.root_cause or len(capa.root_cause.strip()) < 10:
        raise HTTPException(status_code=409, detail="Root cause analysis is required before CAPA submission")
    if not capa.owner_role_code or not capa.verifier_role_code or capa.due_date is None:
        raise HTTPException(status_code=409, detail="CAPA owner, verifier and due date are required")
    actions = active_actions(db, capa.id)
    if not actions:
        raise HTTPException(status_code=409, detail="At least one CAPA action is required")
    incomplete = [x.sequence for x in actions if not x.owner_role_code or x.due_date is None]
    if incomplete:
        raise HTTPException(status_code=409, detail=f"CAPA actions missing owner/due date: {incomplete}")
    return {"action_count": len(actions), "root_cause_present": True}


def validate_implementation_complete(db: Session, capa: Capa) -> dict:
    if capa.status not in {"Approved", "InProgress"}:
        raise HTTPException(status_code=409, detail="CAPA must be Approved or InProgress")
    actions = active_actions(db, capa.id)
    if not actions or any(x.status != "Completed" for x in actions):
        raise HTTPException(status_code=409, detail="All CAPA actions must be Completed")
    return {"completed_actions": len(actions)}


def critical_finding(db: Session, capa: Capa) -> tuple[Finding, MeasurableElement]:
    finding = db.get(Finding, capa.finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    me = db.get(MeasurableElement, finding.measurable_element_id)
    if not me:
        raise HTTPException(status_code=404, detail="Measurable element not found")
    return finding, me


def validate_capa_close(db: Session, capa: Capa) -> dict:
    if capa.status != "EffectivenessPending":
        raise HTTPException(status_code=409, detail="CAPA must be EffectivenessPending before closure")
    actions = active_actions(db, capa.id)
    if not actions or any(x.status != "Completed" for x in actions):
        raise HTTPException(status_code=409, detail="All CAPA actions must remain Completed")
    checks = effectiveness_checks(db, capa.id)
    completed = [x for x in checks if x.status == "Completed"]
    if not completed:
        raise HTTPException(status_code=409, detail="At least one completed effectiveness check is required")
    if any(x.effective is not True for x in completed):
        raise HTTPException(status_code=409, detail="All completed effectiveness checks must be effective")
    finding, me = critical_finding(db, capa)
    return {
        "action_count": len(actions), "effectiveness_checks": len(completed),
        "critical_gate": bool(finding.severity == "P0" or me.esr),
        "me_id": me.me_id,
    }


def reopen_after_failed_check(capa: Capa, finding: Finding, reason: str):
    capa.status = "Reopened"
    capa.reopen_reason = reason
    finding.status = "Reopened"
    finding.closed_at = None
    finding.closure_comment = None
    finding.reopened_count += 1


def now_utc():
    return datetime.now(timezone.utc)
