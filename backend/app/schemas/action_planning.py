from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewSessionCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    title: str = Field(min_length=5, max_length=500)
    scheduled_at: datetime
    chair_role_code: str = Field(default="AccreditationLead", min_length=2, max_length=64)
    quorum_required: int = Field(default=2, ge=1, le=20)
    notes: str | None = Field(default=None, max_length=4000)


class ReviewSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    code: str
    title: str
    scheduled_at: datetime
    status: str
    chair_role_code: str
    quorum_required: int
    notes: str | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ReviewItemCreate(BaseModel):
    recommendation_id: UUID


class ReviewItemDecision(BaseModel):
    decision: Literal["AdoptForPlanning", "Reject", "Defer", "RequestRevision"]
    rationale: str = Field(min_length=5, max_length=4000)


class ReviewItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    session_id: UUID
    recommendation_id: UUID
    sequence: int
    status: str
    decision: str | None = None
    rationale: str | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ActionPlanCreate(BaseModel):
    recommendation_id: UUID
    code: str = Field(min_length=3, max_length=64)
    title: str = Field(min_length=5, max_length=500)
    objective: str = Field(min_length=10, max_length=8000)
    owner_role_code: str = Field(min_length=2, max_length=64)
    verifier_role_code: str = Field(default="CAPAVerifier", min_length=2, max_length=64)
    due_date: date


class ActionPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    recommendation_id: UUID
    measurable_element_id: UUID | None = None
    code: str
    title: str
    objective: str
    owner_role_code: str
    verifier_role_code: str
    due_date: date
    status: str
    human_authorized: bool
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    outcome_summary: str | None = None
    linked_finding_id: UUID | None = None
    linked_capa_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ActionTaskCreate(BaseModel):
    action: str = Field(min_length=5, max_length=8000)
    owner_role_code: str = Field(min_length=2, max_length=64)
    due_date: date


class ActionTaskPatch(BaseModel):
    status: Literal["Open", "InProgress", "Completed", "Cancelled"] | None = None
    evidence_reference: str | None = Field(default=None, max_length=4000)
    completion_note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def completed_requires_note(self):
        if self.status == "Completed" and not self.completion_note:
            raise ValueError("completion_note is required when completing a task")
        return self


class ActionTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    action_plan_id: UUID
    sequence: int
    action: str
    owner_role_code: str
    due_date: date
    status: str
    evidence_reference: str | None = None
    completion_note: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class LifecycleComment(BaseModel):
    comment: str | None = Field(default=None, max_length=4000)


class ActionReviewCreate(BaseModel):
    review_type: Literal["Approval", "CompletionVerification"]
    decision: Literal["Approve", "Reject", "NeedsRevision"]
    comment: str = Field(min_length=5, max_length=4000)
    reviewer_role_code: str = Field(min_length=2, max_length=64)


class ActionReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    action_plan_id: UUID
    review_type: str
    decision: str
    comment: str
    reviewer_role_code: str
    reviewed_at: datetime
    created_at: datetime
    updated_at: datetime


class ConversionRequestCreate(BaseModel):
    target_type: Literal["Finding", "CAPA"]
    severity: Literal["P0", "P1", "P2", "P3"] | None = None
    rationale: str = Field(min_length=10, max_length=4000)


class ConversionDecision(BaseModel):
    approved: bool
    comment: str = Field(min_length=3, max_length=4000)


class ConversionRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    action_plan_id: UUID
    target_type: str
    severity: str | None = None
    rationale: str
    status: str
    requested_at: datetime
    approved_at: datetime | None = None
    executed_at: datetime | None = None
    executed_entity_id: str | None = None
    execution_note: str | None = None
    created_at: datetime
    updated_at: datetime


class ExecuteFinding(BaseModel):
    criterion: str = Field(min_length=3, max_length=500)
    problem_statement: str = Field(min_length=10, max_length=8000)
    owner_role_code: str = Field(min_length=2, max_length=64)
    due_date: date


class ExecuteCapa(BaseModel):
    title: str = Field(min_length=5, max_length=500)
    owner_role_code: str = Field(min_length=2, max_length=64)
    verifier_role_code: str = Field(default="CAPAVerifier", min_length=2, max_length=64)
    due_date: date
    root_cause: str = Field(min_length=10, max_length=8000)
    action_plan: str = Field(min_length=10, max_length=8000)


class ActionPlanComplete(BaseModel):
    outcome_summary: str = Field(min_length=10, max_length=8000)
