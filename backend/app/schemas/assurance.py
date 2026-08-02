from __future__ import annotations
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssuranceProgramRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    code: str
    name: str
    scope: str
    status: str
    cadence_days: int
    lookahead_days: int
    owner_role_code: str
    start_date: date | None = None
    end_date: date | None = None


class AssuranceControlRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    program_id: UUID
    measurable_element_id: UUID
    code: str
    title: str
    critical: bool
    cadence_days: int
    evidence_types: list[str]
    owner_role_code: str
    active: bool
    last_completed_at: datetime | None = None
    next_due_at: datetime | None = None


class AssuranceCycleCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    period_label: str = Field(min_length=3, max_length=64)
    due_at: datetime


class AssuranceCycleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    program_id: UUID
    code: str
    period_label: str
    status: str
    opened_at: datetime
    due_at: datetime
    closed_at: datetime | None = None
    summary_json: dict[str, Any]


class AssuranceTaskComplete(BaseModel):
    result: Literal["Pass", "Fail", "NotApplicable"]
    evidence_reference: str | None = None
    comment: str | None = None

    @model_validator(mode="after")
    def require_context(self):
        if self.result in {"Pass", "Fail"} and not (self.evidence_reference or self.comment):
            raise ValueError("Evidence reference or comment is required")
        return self


class AssuranceTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    cycle_id: UUID
    control_id: UUID
    status: str
    due_at: datetime
    result: str | None = None
    evidence_reference: str | None = None
    comment: str | None = None
    finding_id: UUID | None = None
    completed_at: datetime | None = None


class DataQualityRunCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)


class DataQualityRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    category: str
    severity: str
    owner_role_code: str
    active: bool
    config: dict[str, Any]


class DataQualityRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    code: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    summary_json: dict[str, Any]


class DataQualityIssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    run_id: UUID
    rule_id: UUID
    entity_type: str
    entity_id: str
    message: str
    severity: str
    status: str
    owner_role_code: str
    evidence_reference: str | None = None
    resolved_at: datetime | None = None


class RolloutWaveCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=5, max_length=255)
    planned_start: date
    planned_end: date
    owner_role_code: str = Field(default="AccreditationLead", max_length=64)

    @model_validator(mode="after")
    def validate_window(self):
        if self.planned_end < self.planned_start:
            raise ValueError("planned_end must be on or after planned_start")
        return self


class RolloutWaveRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    template_site_id: UUID
    code: str
    name: str
    status: str
    planned_start: date
    planned_end: date
    owner_role_code: str
    summary_json: dict[str, Any]


class RolloutSiteCreate(BaseModel):
    site_code: str = Field(min_length=2, max_length=32)
    name_ar: str = Field(min_length=2, max_length=255)
    name_en: str = Field(min_length=2, max_length=255)
    site_type: str = Field(default="Hospital", max_length=64)


class RolloutSiteGateUpdate(BaseModel):
    baseline_imported: bool
    users_ready: bool
    training_complete: bool
    deployment_pass: bool
    oidc_pass: bool
    evidence_reference: str | None = None


class RolloutWaveSiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    wave_id: UUID
    site_id: UUID
    status: str
    baseline_imported: bool
    users_ready: bool
    training_complete: bool
    deployment_pass: bool
    oidc_pass: bool
    go_live_ready: bool
    gate_status: dict[str, Any]
