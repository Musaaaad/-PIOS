from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ApplicabilityUpsert(BaseModel):
    decision: Literal["Applicable", "NotApplicable", "Conditional"]
    rationale: str = Field(min_length=20)


class ApplicabilityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    measurable_element_id: UUID
    decision: str
    rationale: str
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReadinessCalculate(BaseModel):
    period_label: str = Field(min_length=3, max_length=64)


class ReadinessSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    captured_at: datetime
    period_label: str
    total_me: int
    applicable_me: int
    not_applicable_me: int
    evidence_sufficient_me: int
    evidence_partial_me: int
    evidence_missing_me: int
    open_p0: int
    open_p1: int
    open_p2: int
    critical_open_actions: bool
    overall_status: str
    esr_status: dict
    details: dict
    calculation_version: str
    readiness_score: int | None


class ReadinessItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    snapshot_id: UUID
    measurable_element_id: UUID
    applicability: str
    evidence_status: str
    open_findings: int
    highest_severity: str | None
    readiness_state: str
    rationale: str
