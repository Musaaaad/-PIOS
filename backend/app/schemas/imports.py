from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class BaselinePayload(BaseModel):
    generated_on: str
    me_registry: list[dict[str, Any]]
    documents: list[dict[str, Any]]


class ImportValidationResult(BaseModel):
    valid: bool
    totals: dict[str, int]
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class ImportCommitResult(BaseModel):
    job_id: str
    status: str
    totals: dict[str, int]


class ImportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_name: str
    idempotency_key: str
    status: str
    dry_run: bool
    totals: dict[str, Any]
    created_at: datetime
    updated_at: datetime
