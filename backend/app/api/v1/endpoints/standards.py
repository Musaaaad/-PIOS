from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, get_principal
from app.db.session import get_db
from app.models.entities import (
    Standard, MeasurableElement, NestedClause, Document, DocumentMeLink, DocumentStandardLink, EvidenceRequest
)
from app.schemas.standards import StandardRead, MeasurableElementRead

router = APIRouter()


def _standard_key(code: str) -> int:
    return int(code.split(".")[1])


def _me_key(me_id: str) -> tuple[int, int]:
    _, standard, element = me_id.split(".")
    return int(standard), int(element)


@router.get("/standards", response_model=list[StandardRead])
def list_standards(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
):
    rows = list(db.scalars(select(Standard)).all())
    return sorted(rows, key=lambda x: _standard_key(x.code))


@router.get("/standards/{standard_code}")
def get_standard(
    standard_code: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
):
    standard = db.scalar(select(Standard).where(Standard.code == standard_code))
    if not standard:
        raise HTTPException(status_code=404, detail="Standard not found")
    mes = list(db.scalars(select(MeasurableElement).where(MeasurableElement.standard_id == standard.id)).all())
    mes.sort(key=lambda x: _me_key(x.me_id))
    return {
        "id": str(standard.id), "code": standard.code, "title": standard.title,
        "source_version": standard.source_version, "active": standard.active,
        "me_count": len(mes), "esr_me_count": sum(1 for x in mes if x.esr),
        "me_ids": [x.me_id for x in mes],
    }


@router.get("/measurable-elements", response_model=list[MeasurableElementRead])
def list_measurable_elements(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
    standard_code: str | None = None,
    esr: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 266,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    stmt = select(MeasurableElement)
    if standard_code:
        stmt = stmt.join(Standard).where(Standard.code == standard_code)
    if esr is not None:
        stmt = stmt.where(MeasurableElement.esr == esr)
    rows = list(db.scalars(stmt).all())
    rows.sort(key=lambda x: _me_key(x.me_id))
    return rows[offset:offset + limit]


@router.get("/measurable-elements/{me_id}", response_model=MeasurableElementRead)
def get_measurable_element(
    me_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
):
    item = db.scalar(select(MeasurableElement).where(MeasurableElement.me_id == me_id))
    if not item:
        raise HTTPException(status_code=404, detail="Measurable element not found")
    return item


@router.get("/measurable-elements/{me_id}/workspace")
def get_me_workspace(
    me_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(get_principal)],
):
    item = db.scalar(select(MeasurableElement).where(MeasurableElement.me_id == me_id))
    if not item:
        raise HTTPException(status_code=404, detail="Measurable element not found")
    clauses = list(db.scalars(
        select(NestedClause)
        .where(NestedClause.measurable_element_id == item.id)
        .order_by(NestedClause.ordinal)
    ).all())
    candidates: dict[str, dict] = {}
    direct_rows = db.execute(
        select(Document, DocumentMeLink)
        .join(DocumentMeLink, DocumentMeLink.document_id == Document.id)
        .where(DocumentMeLink.measurable_element_id == item.id)
    ).all()
    for document, link in direct_rows:
        candidates[str(document.id)] = {
            "id": str(document.id), "code": document.code, "title": document.title,
            "lifecycle_status": document.lifecycle_status, "link_scope": "ME",
            "link_type": link.link_type, "mandatory": link.mandatory,
        }
    standard_docs = db.scalars(
        select(Document)
        .join(DocumentStandardLink, DocumentStandardLink.document_id == Document.id)
        .where(DocumentStandardLink.standard_id == item.standard_id)
    ).all()
    for document in standard_docs:
        candidates.setdefault(str(document.id), {
            "id": str(document.id), "code": document.code, "title": document.title,
            "lifecycle_status": document.lifecycle_status, "link_scope": "Standard",
            "link_type": "Candidate", "mandatory": False,
        })
    return {
        "me": {
            "id": str(item.id), "me_id": item.me_id, "official_text": item.official_text,
            "eoc": item.eoc, "esr": item.esr, "source_page": item.source_page,
        },
        "nested_clauses": [
            {"clause_id": x.clause_id, "ordinal": x.ordinal, "clause_text": x.clause_text}
            for x in clauses
        ],
        "candidate_documents": sorted(candidates.values(), key=lambda x: (x["code"], x["title"])),
        "workspace_state": {
            "document_candidate_count": len(candidates),
            "nested_clause_count": len(clauses),
            "evidence_collection_started": db.scalar(
                select(EvidenceRequest.id).where(EvidenceRequest.measurable_element_id == item.id).limit(1)
            ) is not None,
        },
    }
