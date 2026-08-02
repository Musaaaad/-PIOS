from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

CampaignStatus = Literal["Draft", "Open", "Closed", "Cancelled"]
RequestStatus = Literal[
    "Requested", "InProgress", "Submitted", "UnderReview", "Accepted",
    "PartiallyAccepted", "Rejected", "Contradictory", "Expired", "Cancelled"
]
EvidenceStatus = Literal[
    "Draft", "Submitted", "UnderReview", "Accepted", "PartiallyAccepted",
    "Rejected", "Contradictory", "Expired"
]
ReviewVerdict = Literal["Accepted", "Partial", "Rejected", "Contradictory", "Expired"]
TestResult = Literal["Pass", "Fail", "NotApplicable"]


class CampaignCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    description: str | None = None
    period_start: date
    period_end: date
    site_code: str | None = None

    @model_validator(mode="after")
    def dates_are_valid(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class CampaignLifecycle(BaseModel):
    to_status: CampaignStatus
    comment: str | None = None


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    site_id: UUID
    name: str
    description: str | None
    period_start: date
    period_end: date
    status: CampaignStatus
    opened_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EvidenceRequestCreate(BaseModel):
    me_id: str = Field(pattern=r"^MM\.\d+\.\d+$")
    tool_code: str = Field(min_length=1, max_length=64)
    eoc: list[str] = Field(default_factory=list)
    collector_id: UUID | None = None
    reviewer_id: UUID | None = None
    due_at: datetime | None = None
    instructions: str | None = None


class EvidenceRequestBulkCreate(BaseModel):
    requests: list[EvidenceRequestCreate] = Field(min_length=1, max_length=266)


class EvidenceRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    campaign_id: UUID
    measurable_element_id: UUID
    eoc: list[str]
    tool_code: str
    collector_id: UUID | None
    reviewer_id: UUID | None
    due_at: datetime | None
    status: RequestStatus
    instructions: str | None
    created_at: datetime
    updated_at: datetime


class EvidenceItemCreate(BaseModel):
    source_type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=3, max_length=500)
    description: str | None = None
    structured_data: dict[str, Any] = Field(default_factory=dict)
    period_start: date | None = None
    period_end: date | None = None
    confidentiality: Literal["Internal", "Restricted", "Confidential"] = "Internal"
    sample_size: int | None = Field(default=None, ge=1)
    collected_at: datetime | None = None
    collection_location: str | None = Field(default=None, max_length=255)
    scope_sites: list[str] = Field(default_factory=list)
    scope_shifts: list[str] = Field(default_factory=list)
    coverage_type: Literal["Primary", "Corroborating", "Contextual"] = "Primary"

    @model_validator(mode="after")
    def dates_are_valid(self):
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class EvidenceItemPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=500)
    description: str | None = None
    structured_data: dict[str, Any] | None = None
    period_start: date | None = None
    period_end: date | None = None
    confidentiality: Literal["Internal", "Restricted", "Confidential"] | None = None
    sample_size: int | None = Field(default=None, ge=1)
    collected_at: datetime | None = None
    collection_location: str | None = Field(default=None, max_length=255)


class EvidenceItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID | None
    site_id: UUID
    source_type: str
    status: EvidenceStatus
    period_start: date | None
    period_end: date | None
    confidentiality: str
    title: str
    description: str | None
    structured_data: dict[str, Any]
    sample_size: int | None
    collected_at: datetime | None
    collection_location: str | None
    submitted_by: UUID | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EvidenceFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    evidence_item_id: UUID
    file_name: str
    content_type: str
    size_bytes: int
    storage_uri: str
    sha256: str
    scan_status: str
    scan_message: str | None
    uploaded_at: datetime


class ReviewTestInput(BaseModel):
    test_code: Literal[
        "AUTHENTICITY", "CURRENCY", "SCOPE", "REPRESENTATIVENESS",
        "TRACEABILITY", "CONSISTENCY", "EOC_MATCH"
    ]
    result: TestResult
    comment: str | None = None


class EvidenceReviewCreate(BaseModel):
    verdict: ReviewVerdict
    reason_code: str = Field(min_length=2, max_length=64)
    comment: str | None = None
    tests: list[ReviewTestInput] = Field(min_length=7, max_length=7)
    create_finding: bool = True
    finding_severity: Literal["P0", "P1", "P2"] | None = None
    finding_criterion: str | None = Field(default=None, max_length=500)
    finding_problem_statement: str | None = None


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    evidence_item_id: UUID
    reviewer_id: UUID | None
    verdict: str
    reason_code: str
    comment: str | None
    reviewed_at: datetime


class SubmitResult(BaseModel):
    evidence_item_id: UUID
    request_id: UUID | None
    status: str
    validation: dict[str, Any]


class ReviewResult(BaseModel):
    review: ReviewRead
    evidence_status: str
    request_status: str | None
    finding_id: UUID | None = None
