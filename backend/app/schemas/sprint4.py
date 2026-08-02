from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    category: str
    severity: str
    title: str
    message: str
    entity_type: str | None = None
    entity_id: str | None = None
    action_url: str | None = None
    due_at: datetime | None = None
    status: str
    read_at: datetime | None = None
    created_at: datetime


class NotificationPatch(BaseModel):
    status: Literal["Unread", "Read", "Archived"]


class ExportCreate(BaseModel):
    export_type: Literal["readiness", "findings", "capas", "audit", "executive_pack"]
    file_format: Literal["csv", "json", "zip"] = "csv"
    filters: dict[str, Any] = Field(default_factory=dict)


class ExportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    export_type: str
    file_format: str
    filters: dict[str, Any]
    status: str
    file_name: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
