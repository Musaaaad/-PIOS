from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import Document, DocumentVersion

ALLOWED_TRANSITIONS = {
    "Draft": {"Review"},
    "Review": {"Draft", "Approved"},
    "Approved": {"Review", "Effective"},
    "Effective": {"Superseded", "Retired"},
    "Superseded": {"Retired"},
    "Retired": set(),
}


def transition_document(
    db: Session,
    document: Document,
    to_status: str,
    version_id=None,
) -> tuple[dict, dict]:
    before = {
        "lifecycle_status": document.lifecycle_status,
        "current_version_id": str(document.current_version_id) if document.current_version_id else None,
    }
    allowed = ALLOWED_TRANSITIONS.get(document.lifecycle_status, set())
    if to_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Invalid lifecycle transition: {document.lifecycle_status} -> {to_status}",
        )

    selected_version = None
    if to_status == "Effective":
        if version_id:
            selected_version = db.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.id == version_id,
                    DocumentVersion.document_id == document.id,
                )
            )
        elif document.current_version_id:
            selected_version = db.get(DocumentVersion, document.current_version_id)
        else:
            selected_version = db.scalar(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document.id)
                .order_by(DocumentVersion.created_at.desc())
            )
        if not selected_version:
            raise HTTPException(status_code=409, detail="An approved document version is required")
        if selected_version.status not in {"Approved", "Effective"}:
            raise HTTPException(status_code=409, detail="Selected version must be Approved before activation")

        if document.current_version_id and document.current_version_id != selected_version.id:
            previous = db.get(DocumentVersion, document.current_version_id)
            if previous and previous.status == "Effective":
                previous.status = "Superseded"
        selected_version.status = "Effective"
        document.current_version_id = selected_version.id

    document.lifecycle_status = to_status
    after = {
        "lifecycle_status": document.lifecycle_status,
        "current_version_id": str(document.current_version_id) if document.current_version_id else None,
    }
    return before, after
