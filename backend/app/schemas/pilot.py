from __future__ import annotations
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

PilotStatus = Literal["Draft", "ReadinessReview", "Approved", "Active", "Suspended", "Completed", "RolledBack"]
GateStatus = Literal["Pending", "Pass", "Fail", "Waived"]
UatStatus = Literal["NotRun", "Pass", "Fail", "Blocked"]


class PilotCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{2,63}$")
    name: str = Field(min_length=3, max_length=255)
    objective: str = Field(min_length=10)
    period_start: date
    period_end: date
    owner_role_code: str = "AccreditationLead"
    site_code: str | None = None
    scope_json: dict[str, Any] = Field(default_factory=lambda: {"phase": "P0_ESR", "me_count": 48})

    @model_validator(mode="after")
    def valid_dates(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class PilotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    code: str
    name: str
    objective: str
    scope_json: dict[str, Any]
    period_start: date
    period_end: date
    status: str
    owner_role_code: str
    evidence_campaign_id: UUID | None
    activated_at: datetime | None
    completed_at: datetime | None
    rollback_reason: str | None
    created_at: datetime
    updated_at: datetime


class ParticipantCreate(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    display_name: str = Field(min_length=2, max_length=255)
    role_codes: list[str] = Field(min_length=1, max_length=10)
    external_subject: str | None = Field(default=None, max_length=255)
    training_status: Literal["Pending", "Scheduled", "Complete"] = "Pending"
    access_test_status: Literal["Pending", "Pass", "Fail"] = "Pending"


class ParticipantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    pilot_cycle_id: UUID
    user_id: UUID
    external_subject: str | None
    role_codes: list[str]
    training_status: str
    access_test_status: str
    active: bool
    verified_at: datetime | None
    created_at: datetime


class GateUpdate(BaseModel):
    status: GateStatus
    evidence_reference: str | None = None
    notes: str | None = None


class GateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    pilot_cycle_id: UUID
    gate_code: str
    required: bool
    status: str
    evidence_reference: str | None
    notes: str | None
    checked_at: datetime | None
    created_at: datetime


class PilotLifecycle(BaseModel):
    to_status: PilotStatus
    comment: str | None = None


class UatScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    title_ar: str
    title_en: str
    category: str
    criticality: str
    steps: list[str]
    expected_result: str
    active: bool


class UatExecutionCreate(BaseModel):
    scenario_code: str
    attempt: int = Field(default=1, ge=1, le=20)
    status: UatStatus
    actual_result: str | None = None
    defect_severity: Literal["P0", "P1", "P2"] | None = None
    defect_reference: str | None = None
    evidence_reference: str | None = None


class UatExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    pilot_cycle_id: UUID
    scenario_id: UUID
    attempt: int
    executor_user_id: UUID | None
    status: str
    actual_result: str | None
    defect_severity: str | None
    defect_reference: str | None
    evidence_reference: str | None
    executed_at: datetime | None
    created_at: datetime


class DecisionCreate(BaseModel):
    decision: Literal["Go", "ConditionalGo", "NoGo", "Rollback"]
    rationale: str = Field(min_length=10)
    conditions: list[str] = Field(default_factory=list)


class DecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    pilot_cycle_id: UUID
    decision: str
    rationale: str
    conditions: list[str]
    decided_by: UUID | None
    decided_at: datetime
