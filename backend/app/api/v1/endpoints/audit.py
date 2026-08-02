from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, require_roles
from app.db.session import get_db
from app.models.entities import AuditEvent

router = APIRouter()


@router.get("/audit-events")
def list_audit_events(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[Principal, Depends(require_roles("SystemAdmin", "AccreditationLead", "ReadOnlyAuditor"))],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": str(x.id), "action": x.action, "entity_type": x.entity_type,
            "entity_id": x.entity_id, "trace_id": x.trace_id,
            "created_at": x.created_at,
        }
        for x in rows
    ]
