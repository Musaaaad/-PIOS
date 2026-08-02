from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import add_audit_event
from app.core.config import get_settings
from app.core.security import Principal, require_roles
from app.db.session import get_db
from app.models.entities import Organization, Site, ExportJob
from app.schemas.sprint4 import ExportCreate, ExportJobRead
from app.services.exports import build_export

router = APIRouter()


def _org_site(db: Session):
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.code == settings.organization_code))
    if not org: raise HTTPException(status_code=409, detail="Baseline organization is not seeded")
    site = db.scalar(select(Site).where(Site.organization_id == org.id, Site.code == settings.default_site_code))
    if not site: raise HTTPException(status_code=404, detail="Site not found")
    return org, site


def _actor_uuid(principal: Principal):
    try: return UUID(principal.user_id)
    except (ValueError, TypeError): return None


@router.post("/exports", response_model=ExportJobRead, status_code=201)
def create_export(
    payload: ExportCreate, request: Request, db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "ReadOnlyAuditor"))],
):
    org, site = _org_site(db)
    if payload.export_type == "executive_pack" and payload.file_format != "zip":
        payload.file_format = "zip"
    job = ExportJob(site_id=site.id, requested_by=_actor_uuid(principal), export_type=payload.export_type,
                    file_format=payload.file_format, filters=payload.filters, status="Queued")
    db.add(job); db.flush()
    try:
        build_export(db, get_settings(), site, job)
    except ValueError as exc:
        db.commit(); raise HTTPException(status_code=409, detail=str(exc)) from exc
    add_audit_event(db, request, principal, org.id, "export.create", "ExportJob", str(job.id), after={"type":job.export_type,"format":job.file_format,"status":job.status,"sha256":job.sha256})
    db.commit(); db.refresh(job); return job


@router.get("/exports", response_model=list[ExportJobRead])
def list_exports(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "ReadOnlyAuditor"))],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    _, site = _org_site(db)
    return list(db.scalars(select(ExportJob).where(ExportJob.site_id == site.id).order_by(ExportJob.created_at.desc()).limit(limit)).all())


@router.get("/exports/{export_id}", response_model=ExportJobRead)
def get_export(export_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "ReadOnlyAuditor"))]):
    _, site = _org_site(db); row = db.get(ExportJob, export_id)
    if not row or row.site_id != site.id: raise HTTPException(status_code=404, detail="Export job not found")
    return row


@router.get("/exports/{export_id}/download")
def download_export(export_id: UUID, db: Annotated[Session, Depends(get_db)], _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "MedicationSafety", "ReadOnlyAuditor"))]):
    _, site = _org_site(db); row = db.get(ExportJob, export_id)
    if not row or row.site_id != site.id: raise HTTPException(status_code=404, detail="Export job not found")
    if row.status != "Completed" or not row.storage_uri: raise HTTPException(status_code=409, detail="Export is not ready")
    path = Path(row.storage_uri)
    if not path.exists(): raise HTTPException(status_code=410, detail="Export file is no longer available")
    media = "application/zip" if row.file_format == "zip" else "application/json" if row.file_format == "json" else "text/csv"
    return FileResponse(path, media_type=media, filename=row.file_name)
