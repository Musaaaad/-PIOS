from __future__ import annotations

from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class InstitutionalPilotCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    title: str = Field(min_length=5, max_length=500)
    objective: str = Field(min_length=20)
    run_mode: str = Field(default="Synthetic", pattern="^(Synthetic|Institutional)$")
    period_start: date
    period_end: date
    pilot_cycle_id: UUID | None = None
    committee_id: UUID | None = None
    environment_reference: str | None = None
    oidc_required: bool = True
    institutional_data_required: bool = True

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        if self.run_mode == "Institutional" and not self.environment_reference:
            raise ValueError("Institutional pilot requires an environment reference")
        return self


class InstitutionalPilotRead(ORMModel):
    id: UUID
    site_id: UUID
    pilot_cycle_id: UUID | None
    committee_id: UUID | None
    code: str
    title: str
    objective: str
    run_mode: str
    status: str
    period_start: date
    period_end: date
    environment_reference: str | None
    oidc_required: bool
    institutional_data_required: bool
    activated_at: datetime | None
    observation_started_at: datetime | None
    completed_at: datetime | None
    summary_json: dict


class IdentityBindingCreate(BaseModel):
    external_subject: str = Field(min_length=3, max_length=512)
    issuer: str = Field(min_length=5)
    email_hint: str | None = Field(default=None, max_length=320)
    role_codes: list[str] = Field(min_length=1)
    site_codes: list[str] = Field(min_length=1)
    membership_id: UUID | None = None
    authority_verified: bool = False
    training_verified: bool = False
    site_scope_verified: bool = False
    evidence_reference: str | None = None


class IdentityBindingRead(ORMModel):
    id: UUID
    pilot_run_id: UUID
    user_id: UUID | None
    membership_id: UUID | None
    issuer: str
    subject_hash: str
    email_hint: str | None
    role_codes: list[str]
    site_codes: list[str]
    authority_verified: bool
    training_verified: bool
    site_scope_verified: bool
    verified: bool
    active: bool
    verified_at: datetime | None
    evidence_reference: str | None


class DataSourceAttestationCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    source_system: str = Field(min_length=2, max_length=255)
    source_type: str = Field(min_length=2, max_length=64)
    data_classification: str = Field(pattern="^(Synthetic|Institutional)$")
    period_start: date | None = None
    period_end: date | None = None
    record_count: int = Field(ge=0)
    contains_patient_identifiers: bool = False
    deidentified_or_tokenized: bool = True
    checksum_sha256: str | None = Field(default=None, pattern="^[0-9a-fA-F]{64}$")
    evidence_reference: str = Field(min_length=3)
    attested: bool = True

    @model_validator(mode="after")
    def validate_source(self):
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        if self.contains_patient_identifiers:
            raise ValueError("Pilot attestation must not contain direct patient identifiers")
        if not self.deidentified_or_tokenized:
            raise ValueError("Pilot data must be deidentified or tokenized")
        return self


class DataSourceAttestationRead(ORMModel):
    id: UUID
    pilot_run_id: UUID
    code: str
    source_system: str
    source_type: str
    data_classification: str
    period_start: date | None
    period_end: date | None
    record_count: int
    contains_patient_identifiers: bool
    deidentified_or_tokenized: bool
    checksum_sha256: str | None
    evidence_reference: str
    attested: bool
    attested_at: datetime | None


class PilotSessionLink(BaseModel):
    review_session_id: UUID
    sequence: int = Field(ge=1)
    live_data_attested: bool = False
    evidence_reference: str | None = None


class PilotSessionPatch(BaseModel):
    status: str = Field(pattern="^(Planned|Active|Completed|Cancelled)$")
    evidence_reference: str | None = None


class PilotSessionRead(ORMModel):
    id: UUID
    pilot_run_id: UUID
    review_session_id: UUID
    governance_id: UUID | None
    sequence: int
    status: str
    live_data_attested: bool
    governance_ready: bool
    decision_count: int
    quality_review_count: int
    started_at: datetime | None
    completed_at: datetime | None
    evidence_reference: str | None
    summary_json: dict


class OutcomeMetricCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=3, max_length=255)
    category: str = Field(min_length=2, max_length=64)
    direction: str = Field(default="HigherIsBetter", pattern="^(HigherIsBetter|LowerIsBetter|TargetRange)$")
    baseline_value: float | None = None
    current_value: float | None = None
    target_value: float | None = None
    unit: str = Field(min_length=1, max_length=32)
    source_reference: str | None = None
    owner_role_code: str = Field(default="AccreditationLead", min_length=2, max_length=64)


class OutcomeMetricRead(ORMModel):
    id: UUID
    pilot_run_id: UUID
    code: str
    name: str
    category: str
    direction: str
    baseline_value: float | None
    current_value: float | None
    target_value: float | None
    unit: str
    status: str
    source_reference: str | None
    measured_at: datetime | None
    owner_role_code: str
    guardrail_note: str


class AdoptionEventCreate(BaseModel):
    event_type: str = Field(min_length=2, max_length=64)
    role_code: str | None = Field(default=None, max_length=64)
    actor_reference: str | None = Field(default=None, max_length=512)
    event_count: int = Field(default=1, ge=1)
    occurred_at: datetime | None = None
    evidence_reference: str | None = None
    metadata_json: dict = Field(default_factory=dict)


class AdoptionEventRead(ORMModel):
    id: UUID
    pilot_run_id: UUID
    event_type: str
    role_code: str | None
    actor_token: str | None
    event_count: int
    occurred_at: datetime
    evidence_reference: str | None
    metadata_json: dict


class FeedbackCreate(BaseModel):
    respondent_reference: str = Field(min_length=2, max_length=512)
    role_code: str | None = Field(default=None, max_length=64)
    category: str = Field(min_length=2, max_length=64)
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=4000)
    contains_patient_data: bool = False

    @model_validator(mode="after")
    def validate_privacy(self):
        if self.contains_patient_data:
            raise ValueError("Pilot feedback must not contain patient data")
        return self


class FeedbackRead(ORMModel):
    id: UUID
    pilot_run_id: UUID
    respondent_token: str
    role_code: str | None
    category: str
    rating: int
    comment: str | None
    contains_patient_data: bool
    status: str
    recorded_at: datetime


class OutcomeReportCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    conclusions: str = Field(min_length=30)
    limitations: str = Field(min_length=30)


class OutcomeReportRead(ORMModel):
    id: UUID
    pilot_run_id: UUID
    code: str
    status: str
    data_classification: str
    summary_json: dict
    conclusions: str
    limitations: str
    file_uri: str | None
    sha256: str | None
    generated_at: datetime
    approved_at: datetime | None
    published_at: datetime | None


class ReportPublish(BaseModel):
    file_uri: str = Field(min_length=5)
    sha256: str = Field(pattern="^[0-9a-fA-F]{64}$")


class LifecycleComment(BaseModel):
    comment: str = Field(min_length=15)
