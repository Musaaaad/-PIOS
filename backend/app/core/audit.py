from __future__ import annotations
import uuid
from typing import Any
from fastapi import Request
from sqlalchemy.orm import Session
from app.core.security import Principal
from app.models.entities import AuditEvent


def _actor_uuid(principal: Principal) -> uuid.UUID | None:
    try:
        return uuid.UUID(principal.user_id)
    except (ValueError, TypeError, AttributeError):
        return None


def add_audit_event(
    db: Session,
    request: Request,
    principal: Principal,
    organization_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        actor_id=_actor_uuid(principal),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=before,
        after_json=after,
        trace_id=getattr(request.state, "trace_id", "api"),
    )
    db.add(event)
    return event
