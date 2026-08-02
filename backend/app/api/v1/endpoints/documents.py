from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import add_audit_event
from app.core.config import get_settings
from app.core.security import Principal, get_principal, require_roles
from app.db.session import get_db
from app.models.entities import (
    Organization, Document, DocumentVersion, DocumentStandardLink, DocumentMeLink,
    Standard, MeasurableElement
)
from app.schemas.documents import (
    DocumentCreate, DocumentRead, DocumentVersionCreate, DocumentVersionRead,
    DocumentLifecycleTransition, DocumentMeLinkCreate
)
from app.services.document_workflow import transition_document

router = APIRouter()


def _get_document_or_404(db: Session, document_id: UUID) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
    code: str | None = None,
    lifecycle_status: str | None = None,
    overlap_family: str | None = None,
    query: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    stmt = select(Document)
    if code:
        stmt = stmt.where(Document.code == code)
    if lifecycle_status:
        stmt = stmt.where(Document.lifecycle_status == lifecycle_status)
    if overlap_family:
        stmt = stmt.where(Document.overlap_family == overlap_family)
    if query:
        stmt = stmt.where(Document.title.ilike(f"%{query}%"))
    rows = list(db.scalars(stmt).all())
    rows.sort(key=lambda x: (x.code, x.title))
    return rows[offset:offset + limit]


@router.get("/documents/{document_id}")
def get_document_detail(
    document_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
):
    document = _get_document_or_404(db, document_id)
    versions = list(db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.created_at.desc())
    ).all())
    standard_codes = list(db.scalars(
        select(Standard.code)
        .join(DocumentStandardLink, DocumentStandardLink.standard_id == Standard.id)
        .where(DocumentStandardLink.document_id == document.id)
    ).all())
    me_rows = db.execute(
        select(MeasurableElement.me_id, DocumentMeLink.link_type, DocumentMeLink.mandatory)
        .join(DocumentMeLink, DocumentMeLink.measurable_element_id == MeasurableElement.id)
        .where(DocumentMeLink.document_id == document.id)
    ).all()
    return {
        "document": DocumentRead.model_validate(document).model_dump(mode="json"),
        "versions": [DocumentVersionRead.model_validate(x).model_dump(mode="json") for x in versions],
        "standard_links": sorted(standard_codes, key=lambda x: int(x.split(".")[1])),
        "me_links": [
            {"me_id": row.me_id, "link_type": row.link_type, "mandatory": row.mandatory}
            for row in me_rows
        ],
    }


@router.post("/documents", response_model=DocumentRead, status_code=201)
def create_document(
    payload: DocumentCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))],
):
    settings = get_settings()
    org = db.scalar(select(Organization).where(Organization.code == settings.organization_code))
    if not org:
        raise HTTPException(status_code=409, detail="Baseline organization is not seeded")
    document = Document(organization_id=org.id, **payload.model_dump())
    db.add(document)
    db.flush()
    add_audit_event(
        db, request, principal, org.id, "document.create", "Document", str(document.id),
        after=payload.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(document)
    return document


@router.post("/documents/{document_id}/versions", response_model=DocumentVersionRead, status_code=201)
def create_document_version(
    document_id: UUID,
    payload: DocumentVersionCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))],
):
    document = _get_document_or_404(db, document_id)
    existing = db.scalar(select(DocumentVersion).where(
        DocumentVersion.document_id == document.id,
        DocumentVersion.version_label == payload.version_label,
    ))
    if existing:
        raise HTTPException(status_code=409, detail="Document version label already exists")
    version = DocumentVersion(document_id=document.id, **payload.model_dump())
    db.add(version)
    db.flush()
    add_audit_event(
        db, request, principal, document.organization_id, "document.version.create", "DocumentVersion", str(version.id),
        after=payload.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(version)
    return version


@router.post("/documents/{document_id}/lifecycle", response_model=DocumentRead)
def change_document_lifecycle(
    document_id: UUID,
    payload: DocumentLifecycleTransition,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))],
):
    document = _get_document_or_404(db, document_id)
    before, after = transition_document(db, document, payload.to_status, payload.version_id)
    if payload.comment:
        after["comment"] = payload.comment
    add_audit_event(
        db, request, principal, document.organization_id, "document.lifecycle.transition",
        "Document", str(document.id), before=before, after=after,
    )
    db.commit()
    db.refresh(document)
    return document


@router.post("/documents/{document_id}/links/measurable-elements", status_code=201)
def link_document_to_me(
    document_id: UUID,
    payload: DocumentMeLinkCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "PharmacyDirector"))],
):
    document = _get_document_or_404(db, document_id)
    me = db.scalar(select(MeasurableElement).where(MeasurableElement.me_id == payload.me_id))
    if not me:
        raise HTTPException(status_code=404, detail="Measurable element not found")
    existing = db.scalar(select(DocumentMeLink).where(
        DocumentMeLink.document_id == document.id,
        DocumentMeLink.measurable_element_id == me.id,
        DocumentMeLink.link_type == payload.link_type,
    ))
    if existing:
        return {"id": str(existing.id), "status": "exists"}
    link = DocumentMeLink(
        document_id=document.id, measurable_element_id=me.id,
        link_type=payload.link_type, mandatory=payload.mandatory,
    )
    db.add(link)
    db.flush()
    add_audit_event(
        db, request, principal, document.organization_id, "document.me.link", "DocumentMeLink", str(link.id),
        after=payload.model_dump(mode="json"),
    )
    db.commit()
    return {"id": str(link.id), "status": "created"}
