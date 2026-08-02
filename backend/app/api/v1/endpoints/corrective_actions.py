from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import add_audit_event
from app.core.config import get_settings
from app.core.security import Principal, get_principal, require_roles
from app.db.session import get_db
from app.models.entities import (
    Organization, Site, MeasurableElement, EvidenceItem, Finding, Capa, CapaAction, EffectivenessCheck
)
from app.schemas.capa import (
    FindingCreate, FindingAcknowledge, FindingRead, CapaCreate, CapaPatch, CapaRead,
    CapaActionCreate, CapaActionPatch, CapaActionRead, LifecycleComment,
    EffectivenessCheckCreate, EffectivenessCheckComplete, EffectivenessCheckRead,
)
from app.services.capa_workflow import (
    active_actions, effectiveness_checks, validate_capa_submit,
    validate_implementation_complete, validate_capa_close,
    critical_finding, reopen_after_failed_check, now_utc,
)

router = APIRouter()
OPEN_STATUSES = ["Open", "Acknowledged", "CAPAOpen", "VerificationPending", "Reopened"]


def _actor_uuid(principal: Principal):
    try:
        return UUID(principal.user_id)
    except (ValueError, TypeError):
        return None


def _org_site(db: Session):
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.code == settings.organization_code))
    if not org:
        raise HTTPException(status_code=409, detail="Baseline organization is not seeded")
    site = db.scalar(select(Site).where(Site.organization_id == org.id, Site.code == settings.default_site_code))
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return org, site


def _finding(db: Session, finding_id: UUID) -> Finding:
    row = db.get(Finding, finding_id)
    if not row:
        raise HTTPException(status_code=404, detail="Finding not found")
    return row


def _capa(db: Session, capa_id: UUID) -> Capa:
    row = db.get(Capa, capa_id)
    if not row:
        raise HTTPException(status_code=404, detail="CAPA not found")
    return row


def _action(db: Session, action_id: UUID) -> CapaAction:
    row = db.get(CapaAction, action_id)
    if not row:
        raise HTTPException(status_code=404, detail="CAPA action not found")
    return row


def _check(db: Session, check_id: UUID) -> EffectivenessCheck:
    row = db.get(EffectivenessCheck, check_id)
    if not row:
        raise HTTPException(status_code=404, detail="Effectiveness check not found")
    return row


@router.post("/findings", response_model=FindingRead, status_code=201)
def create_finding(
    payload: FindingCreate, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "EvidenceReviewer", "AccreditationLead", "MedicationSafety"))],
):
    org, site = _org_site(db)
    me = db.scalar(select(MeasurableElement).where(MeasurableElement.me_id == payload.me_id))
    if not me:
        raise HTTPException(status_code=404, detail="Measurable element not found")
    if payload.evidence_item_id and not db.get(EvidenceItem, payload.evidence_item_id):
        raise HTTPException(status_code=404, detail="Evidence item not found")
    severity = "P0" if me.esr else payload.severity
    row = Finding(
        site_id=site.id, measurable_element_id=me.id, evidence_item_id=payload.evidence_item_id,
        source_type=payload.source_type, criterion=payload.criterion, severity=severity,
        problem_statement=payload.problem_statement, owner_role_code=payload.owner_role_code,
        due_date=payload.due_date, status="Open",
    )
    db.add(row); db.flush()
    add_audit_event(db, request, principal, org.id, "finding.create.manual", "Finding", str(row.id), after={**payload.model_dump(mode="json"), "severity": severity})
    db.commit(); db.refresh(row)
    return row


@router.get("/findings")
def list_findings(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "EvidenceReviewer", "AccreditationLead", "MedicationSafety", "MEOwner", "CAPAOwner", "CAPAVerifier", "ReadOnlyAuditor"))],
    severity: str | None = None, status: str | None = None, me_id: str | None = None,
    overdue: bool = False, limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    stmt = select(Finding, MeasurableElement.me_id).join(MeasurableElement, Finding.measurable_element_id == MeasurableElement.id)
    if severity: stmt = stmt.where(Finding.severity == severity)
    if status: stmt = stmt.where(Finding.status == status)
    if me_id: stmt = stmt.where(MeasurableElement.me_id == me_id)
    if overdue:
        stmt = stmt.where(Finding.due_date < datetime.now(timezone.utc).date(), Finding.status.in_(OPEN_STATUSES))
    rows = db.execute(stmt.order_by(Finding.created_at.desc()).limit(limit)).all()
    return [{**FindingRead.model_validate(f).model_dump(mode="json"), "me_id": mid} for f, mid in rows]


@router.get("/findings/{finding_id}")
def finding_workspace(
    finding_id: UUID, db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
):
    finding = _finding(db, finding_id)
    me = db.get(MeasurableElement, finding.measurable_element_id)
    capa = db.scalar(select(Capa).where(Capa.finding_id == finding.id))
    return {
        "finding": FindingRead.model_validate(finding).model_dump(mode="json"),
        "me_id": me.me_id if me else None, "esr": bool(me.esr) if me else False,
        "capa": CapaRead.model_validate(capa).model_dump(mode="json") if capa else None,
        "actions": [CapaActionRead.model_validate(x).model_dump(mode="json") for x in active_actions(db, capa.id)] if capa else [],
        "effectiveness_checks": [EffectivenessCheckRead.model_validate(x).model_dump(mode="json") for x in effectiveness_checks(db, capa.id)] if capa else [],
    }


@router.post("/findings/{finding_id}/acknowledge", response_model=FindingRead)
def acknowledge_finding(
    finding_id: UUID, payload: FindingAcknowledge, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "MEOwner", "CAPAOwner"))],
):
    org, _ = _org_site(db); finding = _finding(db, finding_id)
    if finding.status not in {"Open", "Reopened", "Acknowledged"}:
        raise HTTPException(status_code=409, detail="Finding cannot be acknowledged from its current status")
    before = finding.status
    finding.status = "Acknowledged"; finding.owner_role_code = payload.owner_role_code
    finding.due_date = payload.due_date or finding.due_date; finding.acknowledged_at = now_utc()
    add_audit_event(db, request, principal, org.id, "finding.acknowledge", "Finding", str(finding.id), before={"status": before}, after=payload.model_dump(mode="json") | {"status": finding.status})
    db.commit(); db.refresh(finding); return finding


@router.post("/findings/{finding_id}/capas", response_model=CapaRead, status_code=201)
def create_capa(
    finding_id: UUID, payload: CapaCreate, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "MEOwner", "CAPAOwner"))],
):
    org, _ = _org_site(db); finding = _finding(db, finding_id)
    if finding.status == "Closed":
        raise HTTPException(status_code=409, detail="Closed finding cannot receive a new CAPA")
    existing = db.scalar(select(Capa).where(Capa.finding_id == finding.id))
    if existing:
        return existing
    capa = Capa(finding_id=finding.id, title=payload.title, owner_role_code=payload.owner_role_code,
                verifier_role_code=payload.verifier_role_code, due_date=payload.due_date,
                root_cause=payload.root_cause, action_plan=payload.action_plan, status="Draft")
    db.add(capa); db.flush(); finding.status = "CAPAOpen"
    add_audit_event(db, request, principal, org.id, "capa.create", "Capa", str(capa.id), after=payload.model_dump(mode="json"))
    db.commit(); db.refresh(capa); return capa


@router.get("/capas")
def list_capas(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "MEOwner", "CAPAOwner", "CAPAVerifier", "ReadOnlyAuditor"))],
    status: str | None = None, overdue: bool = False, limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    stmt = select(Capa, Finding.severity, MeasurableElement.me_id).join(Finding, Capa.finding_id == Finding.id).join(MeasurableElement, Finding.measurable_element_id == MeasurableElement.id)
    if status: stmt = stmt.where(Capa.status == status)
    if overdue:
        stmt = stmt.where(Capa.due_date < datetime.now(timezone.utc).date(), Capa.status.notin_(["Closed", "Cancelled"]))
    rows = db.execute(stmt.order_by(Capa.due_date.asc()).limit(limit)).all()
    return [{**CapaRead.model_validate(c).model_dump(mode="json"), "severity": sev, "me_id": mid} for c, sev, mid in rows]


@router.get("/capas/{capa_id}")
def capa_workspace(capa_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(get_principal)]):
    capa = _capa(db, capa_id); finding, me = critical_finding(db, capa)
    return {
        "capa": CapaRead.model_validate(capa).model_dump(mode="json"),
        "finding": FindingRead.model_validate(finding).model_dump(mode="json"),
        "me_id": me.me_id, "esr": me.esr,
        "actions": [CapaActionRead.model_validate(x).model_dump(mode="json") for x in active_actions(db, capa.id)],
        "effectiveness_checks": [EffectivenessCheckRead.model_validate(x).model_dump(mode="json") for x in effectiveness_checks(db, capa.id)],
    }


@router.patch("/capas/{capa_id}", response_model=CapaRead)
def patch_capa(capa_id: UUID, payload: CapaPatch, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "CAPAOwner"))]):
    org, _ = _org_site(db); capa = _capa(db, capa_id)
    if capa.status not in {"Draft", "Reopened"}:
        raise HTTPException(status_code=409, detail="Only Draft or Reopened CAPA can be edited")
    changes = payload.model_dump(exclude_unset=True); before = {k: getattr(capa, k) for k in changes}
    for key, value in changes.items(): setattr(capa, key, value)
    add_audit_event(db, request, principal, org.id, "capa.update", "Capa", str(capa.id), before=before, after=payload.model_dump(mode="json", exclude_unset=True))
    db.commit(); db.refresh(capa); return capa


@router.post("/capas/{capa_id}/actions", response_model=CapaActionRead, status_code=201)
def create_action(capa_id: UUID, payload: CapaActionCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "CAPAOwner"))]):
    org, _ = _org_site(db); capa = _capa(db, capa_id)
    if capa.status not in {"Draft", "Reopened", "Approved", "InProgress"}:
        raise HTTPException(status_code=409, detail="Actions cannot be added in the current CAPA status")
    sequence = (db.scalar(select(func.max(CapaAction.sequence)).where(CapaAction.capa_id == capa.id)) or 0) + 1
    row = CapaAction(capa_id=capa.id, sequence=sequence, action=payload.action, owner_role_code=payload.owner_role_code, due_date=payload.due_date, status="Open")
    db.add(row); db.flush()
    add_audit_event(db, request, principal, org.id, "capa.action.create", "CapaAction", str(row.id), after=payload.model_dump(mode="json") | {"sequence": sequence})
    db.commit(); db.refresh(row); return row


@router.patch("/capa-actions/{action_id}", response_model=CapaActionRead)
def patch_action(action_id: UUID, payload: CapaActionPatch, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "CAPAOwner", "MEOwner"))]):
    org, _ = _org_site(db); row = _action(db, action_id); capa = _capa(db, row.capa_id)
    if capa.status in {"Closed", "Cancelled", "EffectivenessPending"}:
        raise HTTPException(status_code=409, detail="CAPA action is locked")
    changes = payload.model_dump(exclude_unset=True); before = {k: getattr(row, k) for k in changes}
    for key, value in changes.items(): setattr(row, key, value)
    if payload.status == "Completed": row.completed_at = now_utc()
    elif payload.status in {"Open", "InProgress"}: row.completed_at = None
    if capa.status == "Approved" and payload.status in {"InProgress", "Completed"}: capa.status = "InProgress"
    add_audit_event(db, request, principal, org.id, "capa.action.update", "CapaAction", str(row.id), before=before, after=payload.model_dump(mode="json", exclude_unset=True))
    db.commit(); db.refresh(row); return row


@router.post("/capas/{capa_id}/submit", response_model=CapaRead)
def submit_capa(capa_id: UUID, payload: LifecycleComment, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "MedicationSafety", "CAPAOwner"))]):
    org, _ = _org_site(db); capa = _capa(db, capa_id); validation = validate_capa_submit(db, capa)
    capa.status = "Submitted"; capa.submitted_at = now_utc()
    add_audit_event(db, request, principal, org.id, "capa.submit", "Capa", str(capa.id), after={"status": capa.status, "validation": validation, "comment": payload.comment})
    db.commit(); db.refresh(capa); return capa


@router.post("/capas/{capa_id}/approve", response_model=CapaRead)
def approve_capa(capa_id: UUID, payload: LifecycleComment, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "CAPAVerifier"))]):
    org, _ = _org_site(db); capa = _capa(db, capa_id)
    if capa.status != "Submitted": raise HTTPException(status_code=409, detail="Only Submitted CAPA can be approved")
    capa.status = "Approved"; capa.approved_at = now_utc(); capa.approved_by = _actor_uuid(principal)
    add_audit_event(db, request, principal, org.id, "capa.approve", "Capa", str(capa.id), after={"status": capa.status, "comment": payload.comment})
    db.commit(); db.refresh(capa); return capa


@router.post("/capas/{capa_id}/implementation/complete", response_model=CapaRead)
def complete_implementation(capa_id: UUID, payload: LifecycleComment, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "MedicationSafety", "CAPAOwner"))]):
    org, _ = _org_site(db); capa = _capa(db, capa_id); validation = validate_implementation_complete(db, capa)
    capa.status = "ImplementationComplete"; capa.implementation_completed_at = now_utc()
    finding = _finding(db, capa.finding_id); finding.status = "VerificationPending"
    add_audit_event(db, request, principal, org.id, "capa.implementation.complete", "Capa", str(capa.id), after={"status": capa.status, "validation": validation, "comment": payload.comment})
    db.commit(); db.refresh(capa); return capa


@router.post("/capas/{capa_id}/effectiveness-checks", response_model=EffectivenessCheckRead, status_code=201)
def create_effectiveness_check(capa_id: UUID, payload: EffectivenessCheckCreate, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "CAPAVerifier"))]):
    org, _ = _org_site(db); capa = _capa(db, capa_id)
    if capa.status not in {"ImplementationComplete", "EffectivenessPending", "Reopened"}:
        raise HTTPException(status_code=409, detail="Implementation must be complete before effectiveness checks")
    row = EffectivenessCheck(capa_id=capa.id, method=payload.method, target=payload.target, due_date=payload.due_date, sample_size=payload.sample_size, status="Planned")
    db.add(row); db.flush(); capa.status = "EffectivenessPending"
    add_audit_event(db, request, principal, org.id, "effectiveness.create", "EffectivenessCheck", str(row.id), after=payload.model_dump(mode="json"))
    db.commit(); db.refresh(row); return row


@router.post("/effectiveness-checks/{check_id}/complete", response_model=EffectivenessCheckRead)
def complete_effectiveness_check(check_id: UUID, payload: EffectivenessCheckComplete, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "CAPAVerifier"))]):
    org, _ = _org_site(db); row = _check(db, check_id); capa = _capa(db, row.capa_id); finding = _finding(db, capa.finding_id)
    if row.status == "Completed": raise HTTPException(status_code=409, detail="Effectiveness check is already completed")
    row.status = "Completed"; row.result = payload.result; row.effective = payload.effective; row.checked_at = now_utc(); row.checked_by = _actor_uuid(principal)
    if not payload.effective:
        reopen_after_failed_check(capa, finding, payload.result)
    add_audit_event(db, request, principal, org.id, "effectiveness.complete", "EffectivenessCheck", str(row.id), after=payload.model_dump(mode="json") | {"capa_status": capa.status, "finding_status": finding.status})
    db.commit(); db.refresh(row); return row


@router.post("/capas/{capa_id}/close", response_model=CapaRead)
def close_capa(capa_id: UUID, payload: LifecycleComment, request: Request, db: Annotated[Session, Depends(get_db)], principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "CAPAVerifier"))]):
    org, _ = _org_site(db); capa = _capa(db, capa_id); validation = validate_capa_close(db, capa)
    finding, me = critical_finding(db, capa)
    if validation["critical_gate"] and not principal.roles.intersection({"SystemAdmin", "AccreditationLead", "MedicationSafety", "CAPAVerifier"}):
        raise HTTPException(status_code=403, detail="Critical CAPA requires independent verifier")
    capa.status = "Closed"; capa.closed_at = now_utc(); capa.closed_by = _actor_uuid(principal); capa.closure_comment = payload.comment
    finding.status = "Closed"; finding.closed_at = now_utc(); finding.closed_by = _actor_uuid(principal); finding.closure_comment = payload.comment
    add_audit_event(db, request, principal, org.id, "capa.close", "Capa", str(capa.id), after={"status": capa.status, "validation": validation, "comment": payload.comment})
    db.commit(); db.refresh(capa); return capa
