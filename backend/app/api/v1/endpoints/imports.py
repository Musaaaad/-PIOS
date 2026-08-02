import uuid
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import add_audit_event
from app.core.config import get_settings
from app.core.security import Principal, require_roles
from app.db.session import get_db
from app.models.entities import Organization, ImportJob
from app.schemas.imports import BaselinePayload, ImportValidationResult, ImportCommitResult, ImportJobRead
from app.services.import_baseline import validate_baseline
from app.services.seed import seed_baseline

router = APIRouter()


@router.post("/imports/baseline/validate", response_model=ImportValidationResult)
def validate_import(
    payload: BaselinePayload,
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead"))],
):
    return validate_baseline(payload)


@router.post("/imports/baseline/commit", response_model=ImportCommitResult)
def commit_import(
    payload: BaselinePayload,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin"))],
):
    key = request.headers.get("idempotency-key") or str(uuid.uuid4())
    existing = db.scalar(select(ImportJob).where(ImportJob.idempotency_key == key))
    if existing:
        return ImportCommitResult(job_id=str(existing.id), status=existing.status, totals=existing.totals)

    validation = validate_baseline(payload)
    if not validation.valid:
        raise HTTPException(status_code=422, detail=validation.model_dump())

    totals = seed_baseline(db, payload, commit=False)
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.code == settings.organization_code))
    if not org:
        raise HTTPException(status_code=500, detail="Seed did not create baseline organization")
    job = ImportJob(
        organization_id=org.id, source_name="PIOS_MVP_Import_Data_v1.json",
        idempotency_key=key, status="Completed", dry_run=False, totals=totals,
    )
    db.add(job)
    db.flush()
    add_audit_event(
        db, request, principal, org.id, "baseline.import.commit", "ImportJob", str(job.id),
        after={"source_name": job.source_name, "totals": totals, "idempotency_key": key},
    )
    db.commit()
    db.refresh(job)
    return ImportCommitResult(job_id=str(job.id), status=job.status, totals=totals)


@router.get("/imports/jobs", response_model=list[ImportJobRead])
def list_import_jobs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "ReadOnlyAuditor"))],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    return db.scalars(select(ImportJob).order_by(ImportJob.created_at.desc()).limit(limit)).all()


@router.get("/imports/jobs/{job_id}", response_model=ImportJobRead)
def get_import_job(
    job_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "ReadOnlyAuditor"))],
):
    job = db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job
