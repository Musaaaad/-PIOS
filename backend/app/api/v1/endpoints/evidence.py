from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import add_audit_event
from app.core.config import get_settings
from app.core.security import Principal, get_principal, require_roles
from app.db.session import get_db
from app.models.entities import (
    Organization, Site, MeasurableElement, EvidenceCampaign, EvidenceRequest,
    EvidenceItem, EvidenceFile, EvidenceMeLink, EvidenceReview, EvidenceReviewTest, Finding
)
from app.schemas.evidence import (
    CampaignCreate, CampaignLifecycle, CampaignRead, EvidenceRequestBulkCreate,
    EvidenceRequestRead, EvidenceItemCreate, EvidenceItemPatch, EvidenceItemRead,
    EvidenceFileRead, EvidenceReviewCreate, ReviewRead, SubmitResult, ReviewResult
)
from app.services.evidence_storage import store_upload, local_path_from_uri
from app.services.evidence_workflow import (
    transition_campaign, validate_evidence_submission, validate_review_payload,
    request_status_for_verdict, item_status_for_verdict
)

router = APIRouter()


def _actor_uuid(principal: Principal) -> UUID | None:
    try:
        return UUID(principal.user_id)
    except (ValueError, TypeError):
        return None


def _org_and_site(db: Session, site_code: str | None = None) -> tuple[Organization, Site]:
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.code == settings.organization_code))
    if not org:
        raise HTTPException(status_code=409, detail="Baseline organization is not seeded")
    site = db.scalar(select(Site).where(
        Site.organization_id == org.id,
        Site.code == (site_code or settings.default_site_code),
    ))
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return org, site


def _campaign(db: Session, campaign_id: UUID) -> EvidenceCampaign:
    item = db.get(EvidenceCampaign, campaign_id)
    if not item:
        raise HTTPException(status_code=404, detail="Evidence campaign not found")
    return item


def _request(db: Session, request_id: UUID) -> EvidenceRequest:
    item = db.get(EvidenceRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Evidence request not found")
    return item


def _item(db: Session, item_id: UUID) -> EvidenceItem:
    item = db.get(EvidenceItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Evidence item not found")
    return item


@router.post("/evidence-campaigns", response_model=CampaignRead, status_code=201)
def create_campaign(
    payload: CampaignCreate, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))],
):
    org, site = _org_and_site(db, payload.site_code)
    campaign = EvidenceCampaign(
        site_id=site.id, name=payload.name, description=payload.description,
        period_start=payload.period_start, period_end=payload.period_end, status="Draft",
    )
    db.add(campaign); db.flush()
    add_audit_event(db, request, principal, org.id, "evidence.campaign.create", "EvidenceCampaign", str(campaign.id),
                    after=payload.model_dump(mode="json"))
    db.commit(); db.refresh(campaign)
    return campaign


@router.get("/evidence-campaigns", response_model=list[CampaignRead])
def list_campaigns(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    stmt = select(EvidenceCampaign).order_by(EvidenceCampaign.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(EvidenceCampaign.status == status)
    return db.scalars(stmt).all()


@router.get("/evidence-campaigns/{campaign_id}")
def campaign_detail(
    campaign_id: UUID, db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
):
    campaign = _campaign(db, campaign_id)
    status_counts = dict(db.execute(
        select(EvidenceRequest.status, func.count(EvidenceRequest.id))
        .where(EvidenceRequest.campaign_id == campaign.id)
        .group_by(EvidenceRequest.status)
    ).all())
    return {
        "campaign": CampaignRead.model_validate(campaign).model_dump(mode="json"),
        "request_counts": status_counts,
        "total_requests": sum(status_counts.values()),
    }


@router.post("/evidence-campaigns/{campaign_id}/lifecycle", response_model=CampaignRead)
def change_campaign_lifecycle(
    campaign_id: UUID, payload: CampaignLifecycle, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))],
):
    org, _ = _org_and_site(db)
    campaign = _campaign(db, campaign_id)
    before, after = transition_campaign(campaign, payload.to_status)
    if payload.comment:
        after["comment"] = payload.comment
    add_audit_event(db, request, principal, org.id, "evidence.campaign.lifecycle", "EvidenceCampaign", str(campaign.id),
                    before=before, after=after)
    db.commit(); db.refresh(campaign)
    return campaign


@router.post("/evidence-campaigns/{campaign_id}/requests", response_model=list[EvidenceRequestRead], status_code=201)
def create_requests(
    campaign_id: UUID, payload: EvidenceRequestBulkCreate, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector", "MEOwner"))],
):
    org, _ = _org_and_site(db)
    campaign = _campaign(db, campaign_id)
    if campaign.status not in {"Draft", "Open"}:
        raise HTTPException(status_code=409, detail="Requests cannot be added to a closed or cancelled campaign")
    created = []
    for row in payload.requests:
        me = db.scalar(select(MeasurableElement).where(MeasurableElement.me_id == row.me_id))
        if not me:
            raise HTTPException(status_code=404, detail=f"Measurable element not found: {row.me_id}")
        existing = db.scalar(select(EvidenceRequest).where(
            EvidenceRequest.campaign_id == campaign.id,
            EvidenceRequest.measurable_element_id == me.id,
            EvidenceRequest.tool_code == row.tool_code,
        ))
        if existing:
            created.append(existing)
            continue
        req = EvidenceRequest(
            campaign_id=campaign.id, measurable_element_id=me.id,
            eoc=row.eoc or me.eoc, tool_code=row.tool_code,
            collector_id=row.collector_id, reviewer_id=row.reviewer_id,
            due_at=row.due_at, status="Requested", instructions=row.instructions,
        )
        db.add(req); db.flush(); created.append(req)
        add_audit_event(db, request, principal, org.id, "evidence.request.create", "EvidenceRequest", str(req.id),
                        after={"me_id": me.me_id, **row.model_dump(mode="json")})
    db.commit()
    return created


@router.get("/evidence-requests")
def list_requests(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
    campaign_id: UUID | None = None, status: str | None = None, me_id: str | None = None,
    overdue: bool = False, limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    stmt = select(EvidenceRequest, MeasurableElement.me_id).join(
        MeasurableElement, EvidenceRequest.measurable_element_id == MeasurableElement.id
    )
    if campaign_id:
        stmt = stmt.where(EvidenceRequest.campaign_id == campaign_id)
    if status:
        stmt = stmt.where(EvidenceRequest.status == status)
    if me_id:
        stmt = stmt.where(MeasurableElement.me_id == me_id)
    if overdue:
        stmt = stmt.where(
            EvidenceRequest.due_at < datetime.now(timezone.utc),
            EvidenceRequest.status.notin_(["Accepted", "PartiallyAccepted", "Rejected", "Cancelled"]),
        )
    rows = db.execute(stmt.order_by(EvidenceRequest.due_at.asc()).limit(limit)).all()
    return [
        {**EvidenceRequestRead.model_validate(req).model_dump(mode="json"), "me_id": mid}
        for req, mid in rows
    ]


@router.get("/evidence-requests/{request_id}")
def request_detail(
    request_id: UUID, db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
):
    req = _request(db, request_id)
    me = db.get(MeasurableElement, req.measurable_element_id)
    items = list(db.scalars(select(EvidenceItem).where(EvidenceItem.request_id == req.id).order_by(EvidenceItem.created_at)).all())
    return {
        "request": EvidenceRequestRead.model_validate(req).model_dump(mode="json"),
        "me_id": me.me_id if me else None,
        "evidence_items": [EvidenceItemRead.model_validate(x).model_dump(mode="json") for x in items],
    }


@router.post("/evidence-requests/{request_id}/start", response_model=EvidenceRequestRead)
def start_request(
    request_id: UUID, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "EvidenceCollector", "MEOwner"))],
):
    org, _ = _org_and_site(db)
    req = _request(db, request_id)
    campaign = _campaign(db, req.campaign_id)
    if campaign.status != "Open":
        raise HTTPException(status_code=409, detail="Campaign must be Open before collection starts")
    if req.status not in {"Requested", "InProgress"}:
        raise HTTPException(status_code=409, detail="Request cannot be started from its current status")
    before = req.status; req.status = "InProgress"
    add_audit_event(db, request, principal, org.id, "evidence.request.start", "EvidenceRequest", str(req.id),
                    before={"status": before}, after={"status": req.status})
    db.commit(); db.refresh(req)
    return req


@router.post("/evidence-requests/{request_id}/items", response_model=EvidenceItemRead, status_code=201)
def create_evidence_item(
    request_id: UUID, payload: EvidenceItemCreate, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "EvidenceCollector", "MEOwner"))],
):
    org, site = _org_and_site(db)
    req = _request(db, request_id)
    campaign = _campaign(db, req.campaign_id)
    if campaign.status != "Open":
        raise HTTPException(status_code=409, detail="Campaign must be Open")
    if req.status not in {"Requested", "InProgress"}:
        raise HTTPException(status_code=409, detail="Evidence cannot be added to this request")
    item = EvidenceItem(
        request_id=req.id, site_id=site.id, source_type=payload.source_type,
        status="Draft", period_start=payload.period_start, period_end=payload.period_end,
        confidentiality=payload.confidentiality, title=payload.title,
        description=payload.description, structured_data=payload.structured_data,
        sample_size=payload.sample_size, collected_at=payload.collected_at,
        collection_location=payload.collection_location,
    )
    db.add(item); db.flush()
    db.add(EvidenceMeLink(
        evidence_item_id=item.id, measurable_element_id=req.measurable_element_id,
        coverage_type=payload.coverage_type, scope_sites=payload.scope_sites or [get_settings().default_site_code],
        scope_shifts=payload.scope_shifts,
    ))
    req.status = "InProgress"
    add_audit_event(db, request, principal, org.id, "evidence.item.create", "EvidenceItem", str(item.id),
                    after=payload.model_dump(mode="json"))
    db.commit(); db.refresh(item)
    return item


@router.patch("/evidence-items/{item_id}", response_model=EvidenceItemRead)
def patch_evidence_item(
    item_id: UUID, payload: EvidenceItemPatch, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "EvidenceCollector", "MEOwner"))],
):
    org, _ = _org_and_site(db)
    item = _item(db, item_id)
    if item.status != "Draft":
        raise HTTPException(status_code=409, detail="Only Draft evidence can be edited")
    changes = payload.model_dump(exclude_unset=True)
    before = {k: getattr(item, k) for k in changes}
    for key, value in changes.items():
        setattr(item, key, value)
    if item.period_start and item.period_end and item.period_end < item.period_start:
        raise HTTPException(status_code=422, detail="Evidence period is invalid")
    add_audit_event(db, request, principal, org.id, "evidence.item.update", "EvidenceItem", str(item.id),
                    before=before, after=changes)
    db.commit(); db.refresh(item)
    return item


@router.post("/evidence-items/{item_id}/files", response_model=EvidenceFileRead, status_code=201)
def upload_evidence_file(
    item_id: UUID, request: Request,
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "EvidenceCollector", "MEOwner"))],
):
    org, site = _org_and_site(db)
    item = _item(db, item_id)
    if item.status != "Draft":
        raise HTTPException(status_code=409, detail="Files can only be uploaded to Draft evidence")
    req = _request(db, item.request_id) if item.request_id else None
    campaign_id = str(req.campaign_id) if req else "unassigned"
    prefix = f"{org.code}/{site.code}/{campaign_id}/{item.id}"
    stored = store_upload(file, prefix)
    duplicate = db.scalar(select(EvidenceFile).where(
        EvidenceFile.evidence_item_id == item.id,
        EvidenceFile.sha256 == stored.sha256,
    ))
    if duplicate:
        local = local_path_from_uri(stored.storage_uri)
        if local:
            local.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="Duplicate evidence file for this item")
    row = EvidenceFile(
        evidence_item_id=item.id, file_name=file.filename or "evidence.bin",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=stored.size_bytes, storage_uri=stored.storage_uri,
        sha256=stored.sha256, scan_status=stored.scan_status,
        scan_message=stored.scan_message,
    )
    db.add(row); db.flush()
    add_audit_event(db, request, principal, org.id, "evidence.file.upload", "EvidenceFile", str(row.id),
                    after={"file_name": row.file_name, "content_type": row.content_type,
                           "size_bytes": row.size_bytes, "sha256": row.sha256,
                           "scan_status": row.scan_status})
    db.commit(); db.refresh(row)
    return row


@router.get("/evidence-files/{file_id}", response_model=EvidenceFileRead)
def get_evidence_file(
    file_id: UUID, db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
):
    row = db.get(EvidenceFile, file_id)
    if not row:
        raise HTTPException(status_code=404, detail="Evidence file not found")
    return row


@router.get("/evidence-files/{file_id}/download")
def download_evidence_file(
    file_id: UUID, db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "EvidenceCollector", "EvidenceReviewer", "MEOwner", "ReadOnlyAuditor"))],
):
    row = db.get(EvidenceFile, file_id)
    if not row:
        raise HTTPException(status_code=404, detail="Evidence file not found")
    path = local_path_from_uri(row.storage_uri)
    if path is None:
        raise HTTPException(status_code=501, detail="Use the object-storage presigned URL integration for S3 files")
    if not path.exists():
        raise HTTPException(status_code=410, detail="Evidence file object is missing")
    return FileResponse(path, filename=row.file_name, media_type=row.content_type)


@router.post("/evidence-items/{item_id}/submit", response_model=SubmitResult)
def submit_evidence_item(
    item_id: UUID, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "EvidenceCollector", "MEOwner"))],
):
    org, _ = _org_and_site(db)
    item = _item(db, item_id)
    req = _request(db, item.request_id) if item.request_id else None
    if req:
        campaign = _campaign(db, req.campaign_id)
        if campaign.status != "Open":
            raise HTTPException(status_code=409, detail="Campaign must remain Open for submission")
    validation = validate_evidence_submission(db, item)
    item.status = "Submitted"
    item.submitted_at = datetime.now(timezone.utc)
    item.submitted_by = _actor_uuid(principal)
    if req:
        req.status = "Submitted"
    add_audit_event(db, request, principal, org.id, "evidence.item.submit", "EvidenceItem", str(item.id),
                    after={"status": item.status, "validation": validation})
    db.commit()
    return SubmitResult(evidence_item_id=item.id, request_id=req.id if req else None,
                        status=item.status, validation=validation)


@router.post("/evidence-items/{item_id}/review/start", response_model=EvidenceItemRead)
def start_evidence_review(
    item_id: UUID, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "EvidenceReviewer", "AccreditationLead"))],
):
    org, _ = _org_and_site(db)
    item = _item(db, item_id)
    if item.status != "Submitted":
        raise HTTPException(status_code=409, detail="Only Submitted evidence can enter review")
    item.status = "UnderReview"
    req = _request(db, item.request_id) if item.request_id else None
    if req:
        req.status = "UnderReview"
    add_audit_event(db, request, principal, org.id, "evidence.review.start", "EvidenceItem", str(item.id),
                    after={"status": item.status})
    db.commit(); db.refresh(item)
    return item


@router.post("/evidence-items/{item_id}/reviews", response_model=ReviewResult, status_code=201)
def complete_evidence_review(
    item_id: UUID, payload: EvidenceReviewCreate, request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "EvidenceReviewer", "AccreditationLead"))],
):
    org, site = _org_and_site(db)
    item = _item(db, item_id)
    test_data = [x.model_dump() for x in payload.tests]
    validate_review_payload(db, item, payload.verdict, test_data)
    review = EvidenceReview(
        evidence_item_id=item.id, reviewer_id=_actor_uuid(principal),
        verdict=payload.verdict, reason_code=payload.reason_code,
        comment=payload.comment,
    )
    db.add(review); db.flush()
    for test in payload.tests:
        db.add(EvidenceReviewTest(review_id=review.id, **test.model_dump()))
    item.status = item_status_for_verdict(payload.verdict)
    req = _request(db, item.request_id) if item.request_id else None
    if req:
        req.status = request_status_for_verdict(payload.verdict)

    finding_id = None
    if payload.create_finding and payload.verdict != "Accepted":
        me_link = db.scalar(select(EvidenceMeLink).where(EvidenceMeLink.evidence_item_id == item.id))
        me = db.get(MeasurableElement, me_link.measurable_element_id) if me_link else None
        severity = payload.finding_severity or ("P0" if me and me.esr else "P1")
        failed = [x.test_code for x in payload.tests if x.result != "Pass"]
        finding = Finding(
            site_id=site.id,
            measurable_element_id=me.id if me else (req.measurable_element_id if req else None),
            evidence_item_id=item.id,
            criterion=payload.finding_criterion or f"Evidence review for {me.me_id if me else 'ME'}",
            severity=severity,
            problem_statement=payload.finding_problem_statement or
                f"Evidence verdict {payload.verdict}; failed tests: {', '.join(failed)}",
            status="Open",
        )
        if finding.measurable_element_id is None:
            raise HTTPException(status_code=409, detail="Cannot create finding without a measurable-element link")
        db.add(finding); db.flush(); finding_id = finding.id
        add_audit_event(db, request, principal, org.id, "finding.create.from_evidence_review", "Finding", str(finding.id),
                        after={"severity": severity, "verdict": payload.verdict, "failed_tests": failed})

    add_audit_event(db, request, principal, org.id, "evidence.review.complete", "EvidenceReview", str(review.id),
                    after={"verdict": payload.verdict, "reason_code": payload.reason_code,
                           "evidence_status": item.status, "finding_id": str(finding_id) if finding_id else None})
    db.commit(); db.refresh(review)
    return ReviewResult(
        review=ReviewRead.model_validate(review), evidence_status=item.status,
        request_status=req.status if req else None, finding_id=finding_id,
    )


@router.get("/evidence-items/{item_id}")
def evidence_item_detail(
    item_id: UUID, db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
):
    item = _item(db, item_id)
    files = list(db.scalars(select(EvidenceFile).where(EvidenceFile.evidence_item_id == item.id)).all())
    links = db.execute(
        select(MeasurableElement.me_id, EvidenceMeLink.coverage_type,
               EvidenceMeLink.scope_sites, EvidenceMeLink.scope_shifts)
        .join(EvidenceMeLink, EvidenceMeLink.measurable_element_id == MeasurableElement.id)
        .where(EvidenceMeLink.evidence_item_id == item.id)
    ).all()
    reviews = list(db.scalars(select(EvidenceReview).where(EvidenceReview.evidence_item_id == item.id)
                              .order_by(EvidenceReview.reviewed_at.desc())).all())
    return {
        "item": EvidenceItemRead.model_validate(item).model_dump(mode="json"),
        "files": [EvidenceFileRead.model_validate(x).model_dump(mode="json") for x in files],
        "me_links": [{"me_id": x.me_id, "coverage_type": x.coverage_type,
                      "scope_sites": x.scope_sites, "scope_shifts": x.scope_shifts} for x in links],
        "reviews": [ReviewRead.model_validate(x).model_dump(mode="json") for x in reviews],
    }
