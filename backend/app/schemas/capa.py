from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

Severity = Literal["P0", "P1", "P2", "P3"]
FindingStatus = Literal["Open", "Acknowledged", "CAPAOpen", "VerificationPending", "Closed", "Reopened"]
CapaStatus = Literal["Draft", "Submitted", "Approved", "InProgress", "ImplementationComplete", "EffectivenessPending", "Closed", "Reopened", "Cancelled"]
ActionStatus = Literal["Open", "InProgress", "Completed", "Cancelled"]


class FindingCreate(BaseModel):
    me_id: str = Field(pattern=r"^MM\.\d+\.\d+$")
    evidence_item_id: UUID | None = None
    source_type: str = Field(default="Manual", max_length=32)
    criterion: str = Field(min_length=3, max_length=500)
    severity: Severity = "P1"
    problem_statement: str = Field(min_length=10)
    owner_role_code: str | None = Field(default=None, max_length=64)
    due_date: date | None = None


class FindingAcknowledge(BaseModel):
    owner_role_code: str = Field(min_length=2, max_length=64)
    due_date: date | None = None
    comment: str | None = None


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    measurable_element_id: UUID
    evidence_item_id: UUID | None
    source_type: str
    criterion: str
    severity: str
    problem_statement: str
    owner_role_code: str | None
    due_date: date | None
    status: str
    acknowledged_at: datetime | None
    closed_at: datetime | None
    closure_comment: str | None
    reopened_count: int
    created_at: datetime
    updated_at: datetime


class CapaCreate(BaseModel):
    title: str = Field(min_length=5, max_length=500)
    owner_role_code: str = Field(min_length=2, max_length=64)
    verifier_role_code: str = Field(default="CAPAVerifier", min_length=2, max_length=64)
    due_date: date
    root_cause: str | None = None
    action_plan: str = Field(min_length=10)


class CapaPatch(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=500)
    owner_role_code: str | None = Field(default=None, min_length=2, max_length=64)
    verifier_role_code: str | None = Field(default=None, min_length=2, max_length=64)
    due_date: date | None = None
    root_cause: str | None = None
    action_plan: str | None = Field(default=None, min_length=10)


class CapaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    finding_id: UUID
    title: str
    owner_id: UUID | None
    owner_role_code: str | None
    verifier_role_code: str | None
    due_date: date | None
    status: str
    root_cause: str | None
    action_plan: str
    submitted_at: datetime | None
    approved_at: datetime | None
    implementation_completed_at: datetime | None
    closed_at: datetime | None
    closure_comment: str | None
    reopen_reason: str | None
    created_at: datetime
    updated_at: datetime


class CapaActionCreate(BaseModel):
    action: str = Field(min_length=5)
    owner_role_code: str = Field(min_length=2, max_length=64)
    due_date: date


class CapaActionPatch(BaseModel):
    action: str | None = Field(default=None, min_length=5)
    owner_role_code: str | None = Field(default=None, min_length=2, max_length=64)
    due_date: date | None = None
    status: ActionStatus | None = None
    completion_note: str | None = None
    completion_evidence_item_id: UUID | None = None

    @model_validator(mode="after")
    def completion_requires_note(self):
        if self.status == "Completed" and not self.completion_note:
            raise ValueError("completion_note is required when completing an action")
        return self


class CapaActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    capa_id: UUID
    sequence: int
    action: str
    owner_role_code: str | None
    due_date: date | None
    status: str
    completion_note: str | None
    completed_at: datetime | None
    completion_evidence_item_id: UUID | None
    created_at: datetime
    updated_at: datetime


class LifecycleComment(BaseModel):
    comment: str | None = None


class EffectivenessCheckCreate(BaseModel):
    method: str = Field(min_length=10)
    target: str = Field(min_length=3, max_length=500)
    due_date: date
    sample_size: int | None = Field(default=None, ge=1)


class EffectivenessCheckComplete(BaseModel):
    result: str = Field(min_length=5)
    effective: bool


class EffectivenessCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    capa_id: UUID
    method: str
    target: str
    due_date: date | None
    sample_size: int | None
    status: str
    result: str | None
    effective: bool | None
    checked_at: datetime | None
    created_at: datetime
    updated_at: datetime
