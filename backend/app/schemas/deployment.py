from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

CheckStatus = Literal["Pending","Pass","Fail","Waived","Blocked"]

class EnvironmentCreate(BaseModel):
    code: str = Field(min_length=2,max_length=64)
    name: str = Field(min_length=3,max_length=255)
    site_code: str | None = None
    environment_type: Literal["Integration","Pilot","Staging","Production"] = "Pilot"
    api_base_url: str | None = None
    frontend_base_url: str | None = None
    database_kind: str = "PostgreSQL"
    database_version: str | None = None
    object_storage_kind: str = "S3"
    auth_mode: Literal["Dev","OIDC"] = "OIDC"
    oidc_issuer: str | None = None
    release_version: str = "1.1.0"
    release_sha: str | None = None
    tls_enabled: bool = False
    monitoring_enabled: bool = False
    backup_policy_ref: str | None = None

class EnvironmentRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: UUID; site_id: UUID; code: str; name: str; environment_type: str; status: str
    api_base_url: str | None=None; frontend_base_url: str | None=None
    database_kind: str; database_version: str | None=None; object_storage_kind: str
    auth_mode: str; oidc_issuer: str | None=None; release_version: str; release_sha: str | None=None
    tls_enabled: bool; monitoring_enabled: bool; backup_policy_ref: str | None=None; active: bool

class AcceptanceRunCreate(BaseModel):
    run_code: str = Field(min_length=3,max_length=64)
    scope: Literal["BuildVerification","PreGoLive","PostDeploy","Recovery"] = "PreGoLive"
    pilot_cycle_id: UUID | None = None

class CheckUpdate(BaseModel):
    status: CheckStatus
    measured_value: str | None=None
    evidence_reference: str | None=None
    details: str | None=None

class CheckRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: UUID; run_id: UUID; check_code: str; category: str; required: bool; execution_mode: str
    status: str; expected_value: str | None=None; measured_value: str | None=None
    evidence_reference: str | None=None; details: str | None=None; checked_at: datetime | None=None

class AcceptanceRunRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: UUID; environment_id: UUID; pilot_cycle_id: UUID | None=None; run_code: str; scope: str
    status: str; outcome: str; started_at: datetime | None=None; completed_at: datetime | None=None
    summary_json: dict[str,Any]; report_uri: str | None=None; report_sha256: str | None=None

class BackupRestoreCreate(BaseModel):
    run_code: str
    status: Literal["Pending","Pass","Fail"]
    backup_uri: str | None=None; backup_sha256: str | None=None; restore_target: str | None=None
    rpo_seconds: int | None=Field(default=None,ge=0); rto_seconds: int | None=Field(default=None,ge=0)
    row_count_summary: dict[str,Any]=Field(default_factory=dict)
    evidence_reference: str | None=None

class BackupRestoreRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: UUID; environment_id: UUID; run_code: str; status: str
    backup_uri: str | None=None; backup_sha256: str | None=None; restore_target: str | None=None
    rpo_seconds: int | None=None; rto_seconds: int | None=None; row_count_summary: dict[str,Any]
    evidence_reference: str | None=None; restore_completed_at: datetime | None=None

class OidcValidationCreate(BaseModel):
    run_code: str; issuer: str; audience: str
    discovery_url: str | None=None; jwks_url: str | None=None
    discovery_status: Literal["Pending","Pass","Fail"]="Pending"
    jwks_status: Literal["Pending","Pass","Fail"]="Pending"
    token_status: Literal["Pending","Pass","Fail"]="Pending"
    claims_status: Literal["Pending","Pass","Fail"]="Pending"
    required_claims: list[str]=Field(default_factory=lambda:["sub","email","roles","sites"])
    observed_claims: dict[str,Any]=Field(default_factory=dict)
    evidence_reference: str | None=None

class OidcValidationRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: UUID; environment_id: UUID; run_code: str; issuer: str; audience: str
    discovery_url: str | None=None; jwks_url: str | None=None
    discovery_status: str; jwks_status: str; token_status: str; claims_status: str
    required_claims: list[str]; observed_claims: dict[str,Any]; status: str
    evidence_reference: str | None=None; checked_at: datetime | None=None
