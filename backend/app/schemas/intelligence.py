from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class RiskRunCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    period_label: str = Field(min_length=3, max_length=64)

class RiskRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID; site_id: UUID; code: str; period_label: str; status: str
    methodology_version: str; generated_at: datetime; summary_json: dict[str, Any]

class RiskItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID; run_id: UUID; measurable_element_id: UUID; risk_score: int
    risk_band: str; trend: str; signals: list[dict[str, Any]]; rationale: str
    owner_role_code: str | None = None; human_status: str

class AiPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID; organization_id: UUID; code: str; name: str; status: str
    allowed_use_cases: list[str]; prohibited_actions: list[str]
    human_review_required: bool; model_registry: dict[str, Any]

class RecommendationGenerate(BaseModel):
    limit: int = Field(default=10, ge=1, le=25)

class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID; site_id: UUID; risk_run_id: UUID | None = None
    measurable_element_id: UUID | None = None; recommendation_type: str
    title: str; recommendation_text: str; rationale: str; confidence: float
    status: str; source_context: dict[str, Any]; prompt_hash: str; model_id: str
    guardrail_result: dict[str, Any]; decision: str | None = None
    decision_comment: str | None = None; reviewed_at: datetime | None = None

class RecommendationReview(BaseModel):
    decision: Literal["ApprovedForPlanning", "Rejected", "NeedsRevision"]
    comment: str = Field(min_length=3, max_length=2000)

class PortfolioCreate(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    period_label: str = Field(min_length=3, max_length=64)

class PortfolioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID; organization_id: UUID; code: str; period_label: str
    methodology_version: str; generated_at: datetime; summary_json: dict[str, Any]
