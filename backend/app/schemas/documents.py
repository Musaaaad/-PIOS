from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

LifecycleStatus = Literal["Draft", "Review", "Approved", "Effective", "Superseded", "Retired"]
VersionStatus = Literal["Draft", "Review", "Approved", "Effective", "Superseded", "Retired"]


class DocumentCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    document_type: str = Field(min_length=1, max_length=128)
    lifecycle_status: LifecycleStatus = "Draft"
    overlap_family: str | None = None
    notes: str | None = None


class DocumentRead(DocumentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    legacy_evidence_id: str | None = None
    current_version_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DocumentVersionCreate(BaseModel):
    version_label: str = Field(min_length=1, max_length=64)
    status: VersionStatus = "Draft"
    effective_date: date | None = None
    review_date: date | None = None
    source_page_start: int | None = Field(default=None, ge=1)
    source_page_end: int | None = Field(default=None, ge=1)
    file_uri: str | None = None
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    prepared_by: str | None = None
    reviewed_by: str | None = None
    approved_by: str | None = None


class DocumentVersionRead(DocumentVersionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_id: UUID
    created_at: datetime
    updated_at: datetime


class DocumentLifecycleTransition(BaseModel):
    to_status: LifecycleStatus
    version_id: UUID | None = None
    comment: str | None = Field(default=None, max_length=1000)


class DocumentMeLinkCreate(BaseModel):
    me_id: str = Field(pattern=r"^MM\.\d+\.\d+$")
    link_type: Literal["Candidate", "Primary", "Supporting", "Contextual"] = "Candidate"
    mandatory: bool = False
