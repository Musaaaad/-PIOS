from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Site, MeasurableElement, EvidenceRequest, Finding, Capa, CapaAction,
    EffectivenessCheck, ReadinessSnapshot, Notification,
)

OPEN_FINDINGS = {"Open", "Acknowledged", "CAPAOpen", "VerificationPending", "Reopened"}
OPEN_CAPAS = {"Draft", "Submitted", "Approved", "InProgress", "ImplementationComplete", "EffectivenessPending", "Reopened"}


def _upsert_notification(db: Session, *, site_id, fingerprint: str, category: str, severity: str,
                         title: str, message: str, entity_type: str | None = None,
                         entity_id: str | None = None, action_url: str | None = None,
                         due_at=None) -> bool:
    row = db.scalar(select(Notification).where(Notification.site_id == site_id, Notification.fingerprint == fingerprint))
    if row:
        row.category = category; row.severity = severity; row.title = title; row.message = message
        row.entity_type = entity_type; row.entity_id = entity_id; row.action_url = action_url; row.due_at = due_at
        if row.status == "Archived":
            row.status = "Unread"; row.archived_at = None
        return False
    db.add(Notification(
        site_id=site_id, fingerprint=fingerprint, category=category, severity=severity,
        title=title, message=message, entity_type=entity_type, entity_id=entity_id,
        action_url=action_url, due_at=due_at, status="Unread",
    ))
    return True


def refresh_notifications(db: Session, site: Site) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    today = now.date()
    created = 0; refreshed = 0

    requests = db.scalars(select(EvidenceRequest).where(
        EvidenceRequest.due_at.is_not(None), EvidenceRequest.due_at < now,
        EvidenceRequest.status.in_(["Requested", "Collecting", "Returned"]),
    )).all()
    for row in requests:
        is_new = _upsert_notification(db, site_id=site.id, fingerprint=f"evidence-overdue:{row.id}",
            category="Evidence", severity="Warning", title="طلب دليل متأخر",
            message=f"طلب الدليل {row.id} تجاوز موعده المحدد.", entity_type="EvidenceRequest",
            entity_id=str(row.id), action_url=f"#/evidence/{row.id}", due_at=row.due_at)
        created += int(is_new); refreshed += 1

    findings = db.execute(select(Finding, MeasurableElement.me_id).join(
        MeasurableElement, Finding.measurable_element_id == MeasurableElement.id
    ).where(Finding.site_id == site.id, Finding.status.in_(OPEN_FINDINGS), Finding.severity.in_(["P0", "P1"]))).all()
    for row, me_id in findings:
        is_new = _upsert_notification(db, site_id=site.id, fingerprint=f"finding-open:{row.id}",
            category="Finding", severity="Critical" if row.severity == "P0" else "Warning",
            title=f"{row.severity} مفتوح على {me_id}", message=row.problem_statement,
            entity_type="Finding", entity_id=str(row.id), action_url=f"#/findings/{row.id}",
            due_at=datetime.combine(row.due_date, datetime.min.time(), tzinfo=timezone.utc) if row.due_date else None)
        created += int(is_new); refreshed += 1

    capas = db.scalars(select(Capa).where(Capa.due_date.is_not(None), Capa.due_date < today, Capa.status.in_(OPEN_CAPAS))).all()
    for row in capas:
        is_new = _upsert_notification(db, site_id=site.id, fingerprint=f"capa-overdue:{row.id}",
            category="CAPA", severity="Warning", title="CAPA متأخرة", message=row.title,
            entity_type="Capa", entity_id=str(row.id), action_url=f"#/capas/{row.id}",
            due_at=datetime.combine(row.due_date, datetime.min.time(), tzinfo=timezone.utc))
        created += int(is_new); refreshed += 1

    actions = db.scalars(select(CapaAction).where(CapaAction.due_date.is_not(None), CapaAction.due_date < today, CapaAction.status != "Completed")).all()
    for row in actions:
        is_new = _upsert_notification(db, site_id=site.id, fingerprint=f"capa-action-overdue:{row.id}",
            category="CAPAAction", severity="Warning", title="إجراء CAPA متأخر", message=row.action,
            entity_type="CapaAction", entity_id=str(row.id), action_url=f"#/capas/{row.capa_id}",
            due_at=datetime.combine(row.due_date, datetime.min.time(), tzinfo=timezone.utc))
        created += int(is_new); refreshed += 1

    checks = db.scalars(select(EffectivenessCheck).where(EffectivenessCheck.due_date.is_not(None), EffectivenessCheck.due_date < today, EffectivenessCheck.status != "Completed")).all()
    for row in checks:
        is_new = _upsert_notification(db, site_id=site.id, fingerprint=f"effectiveness-overdue:{row.id}",
            category="Effectiveness", severity="Warning", title="اختبار فعالية متأخر", message=row.target,
            entity_type="EffectivenessCheck", entity_id=str(row.id), action_url=f"#/capas/{row.capa_id}",
            due_at=datetime.combine(row.due_date, datetime.min.time(), tzinfo=timezone.utc))
        created += int(is_new); refreshed += 1

    snapshot = db.scalar(select(ReadinessSnapshot).where(ReadinessSnapshot.site_id == site.id).order_by(ReadinessSnapshot.captured_at.desc()).limit(1))
    if snapshot and snapshot.critical_open_actions:
        is_new = _upsert_notification(db, site_id=site.id, fingerprint=f"readiness-critical:{snapshot.id}",
            category="Readiness", severity="Critical", title="Critical Open Actions",
            message="أحدث لقطة جاهزية تحتوي على P0 مفتوح أوESR غير أخضر.",
            entity_type="ReadinessSnapshot", entity_id=str(snapshot.id), action_url="#/readiness")
        created += int(is_new); refreshed += 1

    db.flush()
    return {"created": created, "refreshed": refreshed}
