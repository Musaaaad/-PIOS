from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import uuid
import zipfile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.entities import (
    Site, MeasurableElement, Finding, Capa, AuditEvent,
    ReadinessSnapshot, ReadinessSnapshotItem, ExportJob,
)


def _csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader(); writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


def _readiness_rows(db: Session, site: Site) -> tuple[dict, list[dict]]:
    snapshot = db.scalar(select(ReadinessSnapshot).where(ReadinessSnapshot.site_id == site.id).order_by(ReadinessSnapshot.captured_at.desc()).limit(1))
    if not snapshot:
        raise ValueError("No readiness snapshot exists")
    rows = db.execute(select(ReadinessSnapshotItem, MeasurableElement.me_id).join(
        MeasurableElement, ReadinessSnapshotItem.measurable_element_id == MeasurableElement.id
    ).where(ReadinessSnapshotItem.snapshot_id == snapshot.id).order_by(MeasurableElement.me_id)).all()
    meta = {
        "snapshot_id": str(snapshot.id), "period_label": snapshot.period_label,
        "captured_at": snapshot.captured_at.isoformat(), "readiness_score": snapshot.readiness_score,
        "overall_status": snapshot.overall_status, "critical_open_actions": snapshot.critical_open_actions,
        "applicable_me": snapshot.applicable_me, "not_applicable_me": snapshot.not_applicable_me,
        "evidence_sufficient_me": snapshot.evidence_sufficient_me,
        "evidence_partial_me": snapshot.evidence_partial_me, "evidence_missing_me": snapshot.evidence_missing_me,
        "open_p0": snapshot.open_p0, "open_p1": snapshot.open_p1, "open_p2": snapshot.open_p2,
        "esr_status": snapshot.esr_status,
    }
    detail = [{
        "me_id": me_id, "applicability": item.applicability, "evidence_status": item.evidence_status,
        "open_findings": item.open_findings, "highest_severity": item.highest_severity or "",
        "readiness_state": item.readiness_state, "rationale": item.rationale,
    } for item, me_id in rows]
    return meta, detail


def _finding_rows(db: Session, site: Site) -> list[dict]:
    rows = db.execute(select(Finding, MeasurableElement.me_id).join(
        MeasurableElement, Finding.measurable_element_id == MeasurableElement.id
    ).where(Finding.site_id == site.id).order_by(Finding.created_at.desc())).all()
    return [{
        "id": str(f.id), "me_id": me_id, "severity": f.severity, "status": f.status,
        "criterion": f.criterion, "problem_statement": f.problem_statement,
        "owner_role_code": f.owner_role_code or "", "due_date": f.due_date.isoformat() if f.due_date else "",
        "created_at": f.created_at.isoformat(),
    } for f, me_id in rows]


def _capa_rows(db: Session, site: Site) -> list[dict]:
    rows = db.execute(select(Capa, Finding.severity, MeasurableElement.me_id).join(
        Finding, Capa.finding_id == Finding.id
    ).join(MeasurableElement, Finding.measurable_element_id == MeasurableElement.id).where(
        Finding.site_id == site.id
    ).order_by(Capa.created_at.desc())).all()
    return [{
        "id": str(c.id), "me_id": me_id, "severity": severity, "title": c.title,
        "status": c.status, "owner_role_code": c.owner_role_code or "",
        "verifier_role_code": c.verifier_role_code or "", "due_date": c.due_date.isoformat() if c.due_date else "",
        "created_at": c.created_at.isoformat(),
    } for c, severity, me_id in rows]


def _audit_rows(db: Session, site: Site) -> list[dict]:
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(5000)).all()
    return [{
        "id": str(x.id), "action": x.action, "entity_type": x.entity_type,
        "entity_id": x.entity_id, "trace_id": x.trace_id, "created_at": x.created_at.isoformat(),
    } for x in rows]


def build_export(db: Session, settings: Settings, site: Site, job: ExportJob) -> ExportJob:
    root = Path(settings.export_storage_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    work = root / str(job.id)
    work.mkdir(parents=True, exist_ok=True)
    job.status = "Running"; db.flush()

    try:
        if job.export_type == "readiness":
            meta, rows = _readiness_rows(db, site)
            payload = rows if job.file_format == "csv" else {"snapshot": meta, "items": rows}
        elif job.export_type == "findings":
            payload = _finding_rows(db, site)
        elif job.export_type == "capas":
            payload = _capa_rows(db, site)
        elif job.export_type == "audit":
            payload = _audit_rows(db, site)
        elif job.export_type == "executive_pack":
            payload = None
        else:
            raise ValueError("Unsupported export type")

        if job.export_type == "executive_pack":
            meta, readiness = _readiness_rows(db, site)
            files = {
                "readiness.csv": _csv_bytes(readiness),
                "findings.csv": _csv_bytes(_finding_rows(db, site)),
                "capas.csv": _csv_bytes(_capa_rows(db, site)),
                "audit.csv": _csv_bytes(_audit_rows(db, site)),
                "metadata.json": json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"),
            }
            file_name = f"PIOS_Executive_Pack_{site.code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            path = work / file_name
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for name, content in files.items():
                    z.writestr(name, content)
            job.file_format = "zip"
        else:
            ext = job.file_format
            file_name = f"PIOS_{job.export_type}_{site.code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
            path = work / file_name
            if job.file_format == "csv":
                rows = payload if isinstance(payload, list) else payload.get("items", [])
                path.write_bytes(_csv_bytes(rows))
            elif job.file_format == "json":
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            else:
                raise ValueError("Only csv/json are valid for single exports")

        content = path.read_bytes()
        job.file_name = file_name; job.storage_uri = str(path); job.size_bytes = len(content)
        job.sha256 = hashlib.sha256(content).hexdigest(); job.status = "Completed"
        job.completed_at = datetime.now(timezone.utc)
        job.expires_at = job.completed_at + timedelta(days=settings.export_retention_days)
    except Exception as exc:
        job.status = "Failed"; job.error_message = str(exc)
        raise
    finally:
        db.flush()
    return job
