from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SloRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    code: str
    name: str
    category: str
    indicator_type: str
    target_operator: str
    target_value: float
    unit: str
    window_minutes: int
    severity_on_breach: str
    owner_role_code: str
    active: bool


class SloMeasurementCreate(BaseModel):
    window_start: datetime
    window_end: datetime
    numerator: float | None = None
    denominator: float | None = None
    measured_value: float
    source: str = Field(default="Manual", min_length=2, max_length=128)
    evidence_reference: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_window(self):
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        return self


class SloMeasurementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    objective_id: UUID
    window_start: datetime
    window_end: datetime
    numerator: float | None = None
    denominator: float | None = None
    measured_value: float
    status: str
    source: str
    evidence_reference: str | None = None
    details: dict[str, Any]


class IncidentCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    title: str = Field(min_length=5, max_length=500)
    description: str = Field(min_length=10)
    severity: Literal["P0", "P1", "P2", "P3"]
    category: str = Field(default="Platform", max_length=64)
    source_type: str | None = None
    source_id: str | None = None
    owner_role_code: str = Field(default="SystemAdmin", max_length=64)
    impact_summary: str | None = None
    rollback_required: bool = False


class IncidentTransition(BaseModel):
    to_status: Literal["Acknowledged", "Mitigated", "Resolved", "Closed", "Reopened"]
    note: str = Field(min_length=5)
    evidence_reference: str | None = None
    root_cause: str | None = None
    resolution_summary: str | None = None


class TimelineCreate(BaseModel):
    event_type: str = Field(min_length=2, max_length=64)
    note: str = Field(min_length=5)
    evidence_reference: str | None = None


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    code: str
    title: str
    description: str
    severity: str
    status: str
    category: str
    source_type: str | None = None
    source_id: str | None = None
    owner_role_code: str
    impact_summary: str | None = None
    root_cause: str | None = None
    resolution_summary: str | None = None
    rollback_required: bool
    detected_at: datetime
    acknowledged_at: datetime | None = None
    mitigated_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None


class TimelineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    incident_id: UUID
    event_type: str
    note: str
    status_from: str | None = None
    status_to: str | None = None
    evidence_reference: str | None = None
    occurred_at: datetime


class CutoverCreate(BaseModel):
    environment_id: UUID
    pilot_cycle_id: UUID | None = None
    code: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=5, max_length=255)
    planned_start: datetime
    planned_end: datetime

    @model_validator(mode="after")
    def validate_window(self):
        if self.planned_end <= self.planned_start:
            raise ValueError("planned_end must be after planned_start")
        return self


class CutoverTaskUpdate(BaseModel):
    status: Literal["Pending", "InProgress", "Pass", "Fail", "Skipped", "Blocked"]
    evidence_reference: str | None = None
    details: str | None = None


class CutoverDecision(BaseModel):
    decision: Literal["Go", "NoGo", "Rollback"]
    rationale: str = Field(min_length=10)


class CutoverRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    environment_id: UUID
    pilot_cycle_id: UUID | None = None
    code: str
    name: str
    status: str
    decision: str
    rationale: str | None = None
    planned_start: datetime
    planned_end: datetime
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    rollback_triggered: bool
    summary_json: dict[str, Any]


class CutoverTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    cutover_run_id: UUID
    code: str
    phase: str
    sequence: int
    title: str
    critical: bool
    owner_role_code: str
    planned_offset_min: int
    status: str
    evidence_reference: str | None = None
    details: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class BaselineCreate(BaseModel):
    snapshot_id: UUID
    code: str = Field(min_length=3, max_length=64)
    classification: Literal["OperationalBaseline", "EvidenceReady"] = "OperationalBaseline"


class BaselineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    snapshot_id: UUID
    code: str
    period_label: str
    classification: str
    status: str
    readiness_score: int | None = None
    overall_status: str
    critical_open_actions: bool
    esr_status: dict[str, Any]
    details: dict[str, Any]
    release_uri: str | None = None
    release_sha256: str | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
