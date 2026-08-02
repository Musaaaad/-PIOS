from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class CommitteeCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    name_ar: str = Field(min_length=3, max_length=255)
    name_en: str = Field(min_length=3, max_length=255)
    purpose: str = Field(min_length=20)
    decision_scope: list[str] = Field(min_length=1)
    chair_role_code: str = Field(default="AccreditationLead", min_length=2, max_length=64)
    secretary_role_code: str = Field(default="AccreditationLead", min_length=2, max_length=64)
    quorum_required: int = Field(default=3, ge=2, le=20)
    conflict_policy_reference: str = Field(min_length=5)
    charter_reference: str = Field(min_length=5)
    effective_from: date | None = None
    effective_to: date | None = None


class CommitteeRead(ORMModel):
    id: UUID
    site_id: UUID
    code: str
    name_ar: str
    name_en: str
    purpose: str
    decision_scope: list[str]
    status: str
    chair_role_code: str
    secretary_role_code: str
    quorum_required: int
    conflict_policy_reference: str
    charter_reference: str
    effective_from: date | None
    effective_to: date | None
    activated_at: datetime | None


class MembershipCreate(BaseModel):
    member_code: str = Field(min_length=2, max_length=64)
    display_name: str = Field(min_length=2, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    role_code: str = Field(min_length=2, max_length=64)
    voting_member: bool = True
    chair: bool = False
    secretary: bool = False
    authority_verified: bool = False
    training_verified: bool = False
    term_start: date | None = None
    term_end: date | None = None
    evidence_reference: str | None = None


class MembershipPatch(BaseModel):
    active: bool | None = None
    voting_member: bool | None = None
    authority_verified: bool | None = None
    training_verified: bool | None = None
    evidence_reference: str | None = None


class MembershipRead(ORMModel):
    id: UUID
    committee_id: UUID
    member_code: str
    display_name: str
    email: str | None
    role_code: str
    voting_member: bool
    chair: bool
    secretary: bool
    active: bool
    authority_verified: bool
    training_verified: bool
    term_start: date | None
    term_end: date | None
    evidence_reference: str | None


class GovernanceBind(BaseModel):
    committee_id: UUID


class AttendanceUpsert(BaseModel):
    membership_id: UUID
    attended: bool = True
    voting_eligible: bool = True
    recused: bool = False
    attendance_mode: Literal["InPerson", "Virtual", "Hybrid"] = "InPerson"
    signed_reference: str | None = None


class AttendanceRead(ORMModel):
    id: UUID
    governance_id: UUID
    membership_id: UUID
    attended: bool
    voting_eligible: bool
    recused: bool
    attendance_mode: str
    signed_reference: str | None
    recorded_at: datetime | None


class ConflictDeclarationCreate(BaseModel):
    review_item_id: UUID
    membership_id: UUID
    has_conflict: bool = False
    description: str | None = None
    disposition: Literal["NoConflict", "Recused", "Managed", "PendingResolution"] = "NoConflict"
    evidence_reference: str | None = None

    @model_validator(mode="after")
    def validate_conflict(self):
        if self.has_conflict and not self.description:
            raise ValueError("A conflict description is required")
        if not self.has_conflict and self.disposition != "NoConflict":
            raise ValueError("No-conflict declarations must use NoConflict disposition")
        return self


class ConflictResolve(BaseModel):
    disposition: Literal["Recused", "Managed"]
    comment: str = Field(min_length=5)
    evidence_reference: str | None = None


class ConflictDeclarationRead(ORMModel):
    id: UUID
    governance_id: UUID
    review_item_id: UUID
    membership_id: UUID
    has_conflict: bool
    description: str | None
    disposition: str
    status: str
    declared_at: datetime
    resolved_at: datetime | None
    evidence_reference: str | None


class GovernanceRead(ORMModel):
    id: UUID
    review_session_id: UUID
    committee_id: UUID
    status: str
    expected_voting_members: int
    attended_voting_members: int
    quorum_met: bool
    conflicts_complete: bool
    unresolved_conflicts: int
    authorized_roles: list[str]
    evaluation_json: dict
    evaluated_at: datetime | None


class SlaPolicyCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=3, max_length=255)
    recommendation_to_review_hours: int = Field(default=72, ge=1, le=720)
    review_to_decision_hours: int = Field(default=24, ge=1, le=720)
    decision_to_plan_days: int = Field(default=7, ge=1, le=365)
    plan_to_start_days: int = Field(default=7, ge=1, le=365)
    start_to_completion_days: int = Field(default=30, ge=1, le=730)


class SlaPolicyRead(ORMModel):
    id: UUID
    site_id: UUID
    code: str
    name: str
    recommendation_to_review_hours: int
    review_to_decision_hours: int
    decision_to_plan_days: int
    plan_to_start_days: int
    start_to_completion_days: int
    active: bool
    approved_at: datetime | None


class DecisionQualityReviewCreate(BaseModel):
    review_type: str = "PostDecision"
    rationale_score: int = Field(ge=0, le=5)
    evidence_score: int = Field(ge=0, le=5)
    policy_alignment_score: int = Field(ge=0, le=5)
    conflict_management_score: int = Field(ge=0, le=5)
    bias_check_score: int = Field(ge=0, le=5)
    comment: str = Field(min_length=10)
    reviewer_role_code: str = Field(min_length=2, max_length=64)


class DecisionQualityReviewRead(ORMModel):
    id: UUID
    review_item_id: UUID
    review_type: str
    rationale_score: int
    evidence_score: int
    policy_alignment_score: int
    conflict_management_score: int
    bias_check_score: int
    quality_score: float
    outcome: str
    comment: str
    reviewer_role_code: str
    reviewed_at: datetime


class MetricsSnapshotCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    period_start: datetime
    period_end: datetime

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be after period_start")
        return self


class MetricsSnapshotRead(ORMModel):
    id: UUID
    site_id: UUID
    code: str
    period_start: datetime
    period_end: datetime
    session_count: int
    decision_count: int
    adopted_count: int
    action_plan_count: int
    median_decision_hours: float | None
    p90_decision_hours: float | None
    median_plan_days: float | None
    sla_breach_count: int
    average_quality_score: float | None
    unresolved_conflict_count: int
    summary_json: dict
    generated_at: datetime
