from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
    Integer, Float, String, Text, UniqueConstraint, func, text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import JSONType, UUIDType, RegexCheckConstraint


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Site(Base, TimestampMixin):
    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    site_type: Mapped[str] = mapped_column(String(64), nullable=False, default="Hospital")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Riyadh")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", "site_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))


class Standard(Base, TimestampMixin):
    __tablename__ = "standards"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_version: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MeasurableElement(Base, TimestampMixin):
    __tablename__ = "measurable_elements"
    __table_args__ = (
        RegexCheckConstraint("me_id ~ '^MM\\.[0-9]+\\.[0-9]+$'", name="me_id_format"),
        Index("ix_me_standard_esr", "standard_id", "esr"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    me_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    standard_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("standards.id", ondelete="RESTRICT"), nullable=False)
    official_text: Mapped[str] = mapped_column(Text, nullable=False)
    eoc: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    esr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_version: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_role_code: Mapped[str | None] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class NestedClause(Base):
    __tablename__ = "nested_clauses"
    __table_args__ = (RegexCheckConstraint("clause_id ~ '^MM\\.[0-9]+\\.[0-9]+\\.[0-9]+$'", name="clause_id_format"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    clause_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    measurable_element_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurable_elements.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    clause_text: Mapped[str | None] = mapped_column(Text)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_org_code", "organization_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    legacy_evidence_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    document_type: Mapped[str] = mapped_column(String(128), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    overlap_family: Mapped[str | None] = mapped_column(String(128))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType)
    notes: Mapped[str | None] = mapped_column(Text)


class DocumentVersion(Base, TimestampMixin):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_label"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    effective_date: Mapped[date | None] = mapped_column(Date)
    review_date: Mapped[date | None] = mapped_column(Date)
    source_page_start: Mapped[int | None] = mapped_column(Integer)
    source_page_end: Mapped[int | None] = mapped_column(Integer)
    file_uri: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    prepared_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    approved_by: Mapped[str | None] = mapped_column(String(255))


class DocumentStandardLink(Base):
    __tablename__ = "document_standard_links"
    __table_args__ = (UniqueConstraint("document_id", "standard_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    standard_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("standards.id", ondelete="CASCADE"), nullable=False)


class DocumentMeLink(Base):
    __tablename__ = "document_me_links"
    __table_args__ = (UniqueConstraint("document_id", "measurable_element_id", "link_type"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    measurable_element_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurable_elements.id", ondelete="CASCADE"), nullable=False)
    link_type: Mapped[str] = mapped_column(String(32), nullable=False, default="Candidate")
    mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class EvidenceCampaign(Base, TimestampMixin):
    __tablename__ = "evidence_campaigns"
    __table_args__ = (Index("ix_campaign_site_status_period", "site_id", "status", "period_start", "period_end"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvidenceRequest(Base, TimestampMixin):
    __tablename__ = "evidence_requests"
    __table_args__ = (
        UniqueConstraint("campaign_id", "measurable_element_id", "tool_code"),
        Index("ix_evidence_request_campaign_status_due", "campaign_id", "status", "due_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_campaigns.id", ondelete="CASCADE"), nullable=False)
    measurable_element_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurable_elements.id", ondelete="RESTRICT"), nullable=False)
    eoc: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    tool_code: Mapped[str] = mapped_column(String(64), nullable=False)
    collector_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Requested")
    instructions: Mapped[str | None] = mapped_column(Text)


class EvidenceItem(Base, TimestampMixin):
    __tablename__ = "evidence_items"
    __table_args__ = (Index("ix_evidence_item_site_status_period", "site_id", "status", "period_start", "period_end"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_requests.id", ondelete="SET NULL"))
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    confidentiality: Mapped[str] = mapped_column(String(32), nullable=False, default="Internal")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collection_location: Mapped[str | None] = mapped_column(String(255))
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvidenceFile(Base, TimestampMixin):
    __tablename__ = "evidence_files"
    __table_args__ = (
        UniqueConstraint("evidence_item_id", "sha256"),
        Index("ix_evidence_file_scan_status", "scan_status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(32), nullable=False, default="Clean")
    scan_message: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EvidenceMeLink(Base):
    __tablename__ = "evidence_me_links"
    __table_args__ = (UniqueConstraint("evidence_item_id", "measurable_element_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False)
    measurable_element_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurable_elements.id", ondelete="CASCADE"), nullable=False)
    coverage_type: Mapped[str] = mapped_column(String(32), nullable=False, default="Primary")
    scope_sites: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    scope_shifts: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)


class EvidenceReview(Base, TimestampMixin):
    __tablename__ = "evidence_reviews"
    id: Mapped[uuid.UUID] = uuid_pk()
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EvidenceReviewTest(Base):
    __tablename__ = "evidence_review_tests"
    __table_args__ = (UniqueConstraint("review_id", "test_code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_reviews.id", ondelete="CASCADE"), nullable=False)
    test_code: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)


class Finding(Base, TimestampMixin):
    __tablename__ = "findings"
    __table_args__ = (
        Index("ix_findings_site_severity_status", "site_id", "severity", "status"),
        Index("ix_findings_me_status", "measurable_element_id", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    measurable_element_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurable_elements.id", ondelete="RESTRICT"), nullable=False)
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_items.id", ondelete="SET NULL"))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="EvidenceReview")
    criterion: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False)
    owner_role_code: Mapped[str | None] = mapped_column(String(64))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Open")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closure_comment: Mapped[str | None] = mapped_column(Text)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reopened_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Capa(Base, TimestampMixin):
    __tablename__ = "capas"
    __table_args__ = (
        UniqueConstraint("finding_id"),
        Index("ix_capas_status_due", "status", "due_date"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    owner_role_code: Mapped[str | None] = mapped_column(String(64))
    verifier_role_code: Mapped[str | None] = mapped_column(String(64))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    root_cause: Mapped[str | None] = mapped_column(Text)
    action_plan: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    implementation_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    closure_comment: Mapped[str | None] = mapped_column(Text)
    reopen_reason: Mapped[str | None] = mapped_column(Text)


class CapaAction(Base, TimestampMixin):
    __tablename__ = "capa_actions"
    __table_args__ = (
        UniqueConstraint("capa_id", "sequence"),
        Index("ix_capa_actions_status_due", "status", "due_date"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    capa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("capas.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    owner_role_code: Mapped[str | None] = mapped_column(String(64))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Open")
    completion_note: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_items.id", ondelete="SET NULL"))


class EffectivenessCheck(Base, TimestampMixin):
    __tablename__ = "effectiveness_checks"
    __table_args__ = (Index("ix_effectiveness_capa_status_due", "capa_id", "status", "due_date"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    capa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("capas.id", ondelete="CASCADE"), nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Planned")
    result: Mapped[str | None] = mapped_column(Text)
    effective: Mapped[bool | None] = mapped_column(Boolean)
    checked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApplicabilityDecision(Base, TimestampMixin):
    __tablename__ = "applicability_decisions"
    __table_args__ = (UniqueConstraint("site_id", "measurable_element_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    measurable_element_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurable_elements.id", ondelete="CASCADE"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReadinessSnapshot(Base):
    __tablename__ = "readiness_snapshots"
    __table_args__ = (Index("ix_readiness_site_captured", "site_id", "captured_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    period_label: Mapped[str] = mapped_column(String(64), nullable=False)
    total_me: Mapped[int] = mapped_column(Integer, nullable=False, default=266)
    applicable_me: Mapped[int] = mapped_column(Integer, nullable=False, default=266)
    not_applicable_me: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_sufficient_me: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_partial_me: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_missing_me: Mapped[int] = mapped_column(Integer, nullable=False, default=266)
    open_p0: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_p1: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_p2: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_open_actions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    overall_status: Mapped[str] = mapped_column(String(64), nullable=False, default="NotCalculated")
    esr_status: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    calculation_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    readiness_score: Mapped[int | None] = mapped_column(Integer)


class ReadinessSnapshotItem(Base):
    __tablename__ = "readiness_snapshot_items"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "measurable_element_id"),
        Index("ix_readiness_item_state", "readiness_state", "highest_severity"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("readiness_snapshots.id", ondelete="CASCADE"), nullable=False)
    measurable_element_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurable_elements.id", ondelete="CASCADE"), nullable=False)
    applicability: Mapped[str] = mapped_column(String(32), nullable=False, default="Applicable")
    evidence_status: Mapped[str] = mapped_column(String(32), nullable=False, default="Missing")
    open_findings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    highest_severity: Mapped[str | None] = mapped_column(String(8))
    readiness_state: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("site_id", "fingerprint"),
        Index("ix_notifications_site_status_created", "site_id", "status", "created_at"),
        Index("ix_notifications_severity_due", "severity", "due_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="Info")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(128))
    entity_id: Mapped[str | None] = mapped_column(String(128))
    action_url: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Unread")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExportJob(Base, TimestampMixin):
    __tablename__ = "export_jobs"
    __table_args__ = (
        Index("ix_export_jobs_site_status_created", "site_id", "status", "created_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    export_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_format: Mapped[str] = mapped_column(String(16), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Queued")
    file_name: Mapped[str | None] = mapped_column(String(500))
    storage_uri: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class PilotCycle(Base, TimestampMixin):
    __tablename__ = "pilot_cycles"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        Index("ix_pilot_site_status_period", "site_id", "status", "period_start", "period_end"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    owner_role_code: Mapped[str] = mapped_column(String(64), nullable=False, default="AccreditationLead")
    evidence_campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_campaigns.id", ondelete="SET NULL"))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rollback_reason: Mapped[str | None] = mapped_column(Text)


class PilotParticipant(Base, TimestampMixin):
    __tablename__ = "pilot_participants"
    __table_args__ = (
        UniqueConstraint("pilot_cycle_id", "user_id"),
        Index("ix_pilot_participant_status", "pilot_cycle_id", "training_status", "access_test_status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    pilot_cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pilot_cycles.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    external_subject: Mapped[str | None] = mapped_column(String(255))
    role_codes: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    training_status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    access_test_status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PilotGateCheck(Base, TimestampMixin):
    __tablename__ = "pilot_gate_checks"
    __table_args__ = (
        UniqueConstraint("pilot_cycle_id", "gate_code"),
        Index("ix_pilot_gate_status", "pilot_cycle_id", "required", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    pilot_cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pilot_cycles.id", ondelete="CASCADE"), nullable=False)
    gate_code: Mapped[str] = mapped_column(String(64), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    checked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UatScenario(Base, TimestampMixin):
    __tablename__ = "uat_scenarios"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    title_ar: Mapped[str] = mapped_column(String(500), nullable=False)
    title_en: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    criticality: Mapped[str] = mapped_column(String(8), nullable=False, default="P2")
    steps: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UatExecution(Base, TimestampMixin):
    __tablename__ = "uat_executions"
    __table_args__ = (
        UniqueConstraint("pilot_cycle_id", "scenario_id", "attempt"),
        Index("ix_uat_execution_status", "pilot_cycle_id", "status", "defect_severity"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    pilot_cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pilot_cycles.id", ondelete="CASCADE"), nullable=False)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uat_scenarios.id", ondelete="RESTRICT"), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    executor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NotRun")
    actual_result: Mapped[str | None] = mapped_column(Text)
    defect_severity: Mapped[str | None] = mapped_column(String(8))
    defect_reference: Mapped[str | None] = mapped_column(String(128))
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PilotDecision(Base, TimestampMixin):
    __tablename__ = "pilot_decisions"
    __table_args__ = (Index("ix_pilot_decision_cycle_created", "pilot_cycle_id", "created_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    pilot_cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pilot_cycles.id", ondelete="CASCADE"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    conditions: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DeploymentEnvironment(Base, TimestampMixin):
    __tablename__ = "deployment_environments"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        Index("ix_deployment_env_site_status", "site_id", "status", "environment_type"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="Pilot")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    api_base_url: Mapped[str | None] = mapped_column(Text)
    frontend_base_url: Mapped[str | None] = mapped_column(Text)
    database_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="PostgreSQL")
    database_version: Mapped[str | None] = mapped_column(String(64))
    object_storage_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="S3")
    auth_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="OIDC")
    oidc_issuer: Mapped[str | None] = mapped_column(Text)
    release_version: Mapped[str] = mapped_column(String(64), nullable=False)
    release_sha: Mapped[str | None] = mapped_column(String(128))
    tls_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    backup_policy_ref: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DeploymentAcceptanceRun(Base, TimestampMixin):
    __tablename__ = "deployment_acceptance_runs"
    __table_args__ = (
        UniqueConstraint("environment_id", "run_code"),
        Index("ix_acceptance_run_env_status", "environment_id", "status", "started_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    environment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deployment_environments.id", ondelete="CASCADE"), nullable=False)
    pilot_cycle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pilot_cycles.id", ondelete="SET NULL"))
    run_code: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="PreGoLive")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="NotAssessed")
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    report_uri: Mapped[str | None] = mapped_column(Text)
    report_sha256: Mapped[str | None] = mapped_column(String(64))


class DeploymentAcceptanceCheck(Base, TimestampMixin):
    __tablename__ = "deployment_acceptance_checks"
    __table_args__ = (
        UniqueConstraint("run_id", "check_code"),
        Index("ix_acceptance_check_run_status", "run_id", "required", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deployment_acceptance_runs.id", ondelete="CASCADE"), nullable=False)
    check_code: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="Manual")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    expected_value: Mapped[str | None] = mapped_column(Text)
    measured_value: Mapped[str | None] = mapped_column(Text)
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    details: Mapped[str | None] = mapped_column(Text)
    checked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BackupRestoreRun(Base, TimestampMixin):
    __tablename__ = "backup_restore_runs"
    __table_args__ = (
        UniqueConstraint("environment_id", "run_code"),
        Index("ix_backup_restore_env_status", "environment_id", "status", "restore_completed_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    environment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deployment_environments.id", ondelete="CASCADE"), nullable=False)
    run_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    backup_uri: Mapped[str | None] = mapped_column(Text)
    backup_sha256: Mapped[str | None] = mapped_column(String(64))
    restore_target: Mapped[str | None] = mapped_column(String(255))
    backup_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    backup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restore_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restore_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rpo_seconds: Mapped[int | None] = mapped_column(Integer)
    rto_seconds: Mapped[int | None] = mapped_column(Integer)
    row_count_summary: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    executed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class OidcValidationRun(Base, TimestampMixin):
    __tablename__ = "oidc_validation_runs"
    __table_args__ = (
        UniqueConstraint("environment_id", "run_code"),
        Index("ix_oidc_validation_env_status", "environment_id", "status", "checked_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    environment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deployment_environments.id", ondelete="CASCADE"), nullable=False)
    run_code: Mapped[str] = mapped_column(String(64), nullable=False)
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[str] = mapped_column(String(255), nullable=False)
    discovery_url: Mapped[str | None] = mapped_column(Text)
    jwks_url: Mapped[str | None] = mapped_column(Text)
    discovery_status: Mapped[str] = mapped_column(String(16), nullable=False, default="Pending")
    jwks_status: Mapped[str] = mapped_column(String(16), nullable=False, default="Pending")
    token_status: Mapped[str] = mapped_column(String(16), nullable=False, default="Pending")
    claims_status: Mapped[str] = mapped_column(String(16), nullable=False, default="Pending")
    required_claims: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    observed_claims: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    checked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_entity_time", "entity_type", "entity_id", "created_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ImportJob(Base, TimestampMixin):
    __tablename__ = "import_jobs"
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    totals: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class ImportJobError(Base):
    __tablename__ = "import_job_errors"
    id: Mapped[uuid.UUID] = uuid_pk()
    import_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    field: Mapped[str | None] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONType)


class ServiceLevelObjective(Base, TimestampMixin):
    __tablename__ = "service_level_objectives"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        Index("ix_slo_site_active_category", "site_id", "active", "category"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    indicator_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_operator: Mapped[str] = mapped_column(String(8), nullable=False, default=">=")
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    severity_on_breach: Mapped[str] = mapped_column(String(8), nullable=False, default="P1")
    owner_role_code: Mapped[str] = mapped_column(String(64), nullable=False, default="SystemAdmin")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ServiceLevelMeasurement(Base, TimestampMixin):
    __tablename__ = "service_level_measurements"
    __table_args__ = (
        UniqueConstraint("objective_id", "window_start", "window_end"),
        Index("ix_slo_measurement_status_window", "status", "window_end"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    objective_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_level_objectives.id", ondelete="CASCADE"), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    numerator: Mapped[float | None] = mapped_column(Float)
    denominator: Mapped[float | None] = mapped_column(Float)
    measured_value: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="Pending")
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="Manual")
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class OperationalIncident(Base, TimestampMixin):
    __tablename__ = "operational_incidents"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        Index("ix_operational_incident_site_status_severity", "site_id", "status", "severity"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Open")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="Platform")
    source_type: Mapped[str | None] = mapped_column(String(128))
    source_id: Mapped[str | None] = mapped_column(String(128))
    owner_role_code: Mapped[str] = mapped_column(String(64), nullable=False, default="SystemAdmin")
    impact_summary: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    rollback_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mitigated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class IncidentTimelineEntry(Base):
    __tablename__ = "incident_timeline_entries"
    __table_args__ = (Index("ix_incident_timeline_incident_time", "incident_id", "occurred_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operational_incidents.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    status_from: Mapped[str | None] = mapped_column(String(32))
    status_to: Mapped[str | None] = mapped_column(String(32))
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CutoverRun(Base, TimestampMixin):
    __tablename__ = "cutover_runs"
    __table_args__ = (
        UniqueConstraint("environment_id", "code"),
        Index("ix_cutover_env_status_start", "environment_id", "status", "planned_start"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    environment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deployment_environments.id", ondelete="CASCADE"), nullable=False)
    pilot_cycle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pilot_cycles.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    rationale: Mapped[str | None] = mapped_column(Text)
    planned_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planned_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rollback_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class CutoverTask(Base, TimestampMixin):
    __tablename__ = "cutover_tasks"
    __table_args__ = (
        UniqueConstraint("cutover_run_id", "code"),
        Index("ix_cutover_task_run_phase_status", "cutover_run_id", "phase", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    cutover_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cutover_runs.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    owner_role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    planned_offset_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    details: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class BaselineRelease(Base, TimestampMixin):
    __tablename__ = "baseline_releases"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        Index("ix_baseline_release_site_status_published", "site_id", "status", "published_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("readiness_snapshots.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    period_label: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False, default="OperationalBaseline")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    readiness_score: Mapped[int | None] = mapped_column(Integer)
    overall_status: Mapped[str] = mapped_column(String(64), nullable=False)
    critical_open_actions: Mapped[bool] = mapped_column(Boolean, nullable=False)
    esr_status: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    release_uri: Mapped[str | None] = mapped_column(Text)
    release_sha256: Mapped[str | None] = mapped_column(String(64))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssuranceProgram(Base, TimestampMixin):
    __tablename__ = "assurance_programs"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        Index("ix_assurance_program_site_status", "site_id", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, default="P0_ESR")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Active")
    cadence_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    lookahead_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    owner_role_code: Mapped[str] = mapped_column(String(64), nullable=False, default="AccreditationLead")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AssuranceControl(Base, TimestampMixin):
    __tablename__ = "assurance_controls"
    __table_args__ = (
        UniqueConstraint("program_id", "measurable_element_id"),
        Index("ix_assurance_control_due_active", "active", "next_due_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assurance_programs.id", ondelete="CASCADE"), nullable=False)
    measurable_element_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurable_elements.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cadence_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    evidence_types: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    owner_role_code: Mapped[str] = mapped_column(String(64), nullable=False, default="MEOwner")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssuranceCycle(Base, TimestampMixin):
    __tablename__ = "assurance_cycles"
    __table_args__ = (
        UniqueConstraint("program_id", "code"),
        Index("ix_assurance_cycle_program_status_due", "program_id", "status", "due_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assurance_programs.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    period_label: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Open")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AssuranceTask(Base, TimestampMixin):
    __tablename__ = "assurance_tasks"
    __table_args__ = (
        UniqueConstraint("cycle_id", "control_id"),
        Index("ix_assurance_task_cycle_status_due", "cycle_id", "status", "due_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assurance_cycles.id", ondelete="CASCADE"), nullable=False)
    control_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assurance_controls.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result: Mapped[str | None] = mapped_column(String(32))
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataQualityRule(Base, TimestampMixin):
    __tablename__ = "data_quality_rules"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="P2")
    owner_role_code: Mapped[str] = mapped_column(String(64), nullable=False, default="SystemAdmin")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class DataQualityRun(Base, TimestampMixin):
    __tablename__ = "data_quality_runs"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        Index("ix_data_quality_run_site_status", "site_id", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class DataQualityIssue(Base, TimestampMixin):
    __tablename__ = "data_quality_issues"
    __table_args__ = (
        Index("ix_data_quality_issue_run_status_severity", "run_id", "status", "severity"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_quality_runs.id", ondelete="CASCADE"), nullable=False)
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_quality_rules.id", ondelete="RESTRICT"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Open")
    owner_role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RolloutWave(Base, TimestampMixin):
    __tablename__ = "rollout_waves"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        Index("ix_rollout_wave_org_status_start", "organization_id", "status", "planned_start"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    template_site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    planned_start: Mapped[date] = mapped_column(Date, nullable=False)
    planned_end: Mapped[date] = mapped_column(Date, nullable=False)
    owner_role_code: Mapped[str] = mapped_column(String(64), nullable=False, default="AccreditationLead")
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class RolloutWaveSite(Base, TimestampMixin):
    __tablename__ = "rollout_wave_sites"
    __table_args__ = (
        UniqueConstraint("wave_id", "site_id"),
        Index("ix_rollout_wave_site_status_ready", "wave_id", "status", "go_live_ready"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    wave_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rollout_waves.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Planned")
    baseline_imported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    users_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    training_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deployment_pass: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    oidc_pass: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    go_live_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gate_status: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class RiskAssessmentRun(Base, TimestampMixin):
    __tablename__ = "risk_assessment_runs"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        Index("ix_risk_run_site_generated", "site_id", "generated_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    period_label: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Completed")
    methodology_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class RiskAssessmentItem(Base, TimestampMixin):
    __tablename__ = "risk_assessment_items"
    __table_args__ = (
        UniqueConstraint("run_id", "measurable_element_id"),
        Index("ix_risk_item_run_band_score", "run_id", "risk_band", "risk_score"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("risk_assessment_runs.id", ondelete="CASCADE"), nullable=False)
    measurable_element_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("measurable_elements.id", ondelete="RESTRICT"), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_band: Mapped[str] = mapped_column(String(16), nullable=False)
    trend: Mapped[str] = mapped_column(String(16), nullable=False, default="Unknown")
    signals: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False, default=list)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    owner_role_code: Mapped[str | None] = mapped_column(String(64))
    human_status: Mapped[str] = mapped_column(String(32), nullable=False, default="Unreviewed")


class AiGovernancePolicy(Base, TimestampMixin):
    __tablename__ = "ai_governance_policies"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Effective")
    allowed_use_cases: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    prohibited_actions: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    model_registry: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiRecommendation(Base, TimestampMixin):
    __tablename__ = "ai_recommendations"
    __table_args__ = (
        Index("ix_ai_recommendation_site_status_created", "site_id", "status", "created_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    risk_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("risk_assessment_runs.id", ondelete="SET NULL"))
    measurable_element_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("measurable_elements.id", ondelete="SET NULL"))
    recommendation_type: Mapped[str] = mapped_column(String(64), nullable=False, default="RiskReduction")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    recommendation_text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NeedsHumanReview")
    source_context: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False, default="rules-engine-v1")
    guardrail_result: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision: Mapped[str | None] = mapped_column(String(32))
    decision_comment: Mapped[str | None] = mapped_column(Text)


class PortfolioSnapshot(Base, TimestampMixin):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    period_label: Mapped[str] = mapped_column(String(64), nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class PortfolioSiteMetric(Base, TimestampMixin):
    __tablename__ = "portfolio_site_metrics"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "site_id"),
        Index("ix_portfolio_metric_snapshot_status", "snapshot_id", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    readiness_score: Mapped[int | None] = mapped_column(Integer)
    risk_score: Mapped[int | None] = mapped_column(Integer)
    open_p0: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_p1: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    esr_red: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_quality_issues: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overdue_controls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class ReleasePackage(Base, TimestampMixin):
    __tablename__ = "release_packages"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        Index("ix_release_package_org_status_created", "organization_id", "status", "created_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    release_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    artifact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluation_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReleaseArtifact(Base, TimestampMixin):
    __tablename__ = "release_artifacts"
    __table_args__ = (
        UniqueConstraint("release_package_id", "name"),
        Index("ix_release_artifact_package_type", "release_package_id", "artifact_type"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    release_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("release_packages.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    media_type: Mapped[str | None] = mapped_column(String(128))
    signed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    signature_reference: Mapped[str | None] = mapped_column(Text)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SecurityControlAssessment(Base, TimestampMixin):
    __tablename__ = "security_control_assessments"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        Index("ix_security_control_org_status_severity", "organization_id", "status", "severity"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="P1")
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="Pending")
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    checked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RetentionPolicy(Base, TimestampMixin):
    __tablename__ = "retention_policies"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    legal_basis: Mapped[str] = mapped_column(Text, nullable=False)
    purge_method: Mapped[str] = mapped_column(String(64), nullable=False, default="SoftDeleteThenPurge")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LegalHold(Base, TimestampMixin):
    __tablename__ = "legal_holds"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        Index("ix_legal_hold_org_status_scope", "organization_id", "status", "scope_type"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="Active")
    placed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    released_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_reason: Mapped[str | None] = mapped_column(Text)


class AuditExportPackage(Base, TimestampMixin):
    __tablename__ = "audit_export_packages"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        Index("ix_audit_export_org_status_created", "organization_id", "status", "created_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="Generated")
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    root_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntelligenceReviewSession(Base, TimestampMixin):
    __tablename__ = "intelligence_review_sessions"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        Index("ix_intelligence_review_site_status_date", "site_id", "status", "scheduled_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    chair_role_code: Mapped[str] = mapped_column(String(64), nullable=False, default="AccreditationLead")
    quorum_required: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    notes: Mapped[str | None] = mapped_column(Text)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class IntelligenceReviewItem(Base, TimestampMixin):
    __tablename__ = "intelligence_review_items"
    __table_args__ = (
        UniqueConstraint("session_id", "recommendation_id", name="uq_intelligence_review_items_session_recommendation"),
        UniqueConstraint("session_id", "sequence", name="uq_intelligence_review_items_session_sequence"),
        Index("ix_intelligence_review_item_session_status", "session_id", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intelligence_review_sessions.id", ondelete="CASCADE"), nullable=False)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_recommendations.id", ondelete="RESTRICT"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    decision: Mapped[str | None] = mapped_column(String(32))
    rationale: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntelligenceActionPlan(Base, TimestampMixin):
    __tablename__ = "intelligence_action_plans"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        UniqueConstraint("recommendation_id"),
        Index("ix_intelligence_action_plan_site_status_due", "site_id", "status", "due_date"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_recommendations.id", ondelete="RESTRICT"), nullable=False)
    measurable_element_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("measurable_elements.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    owner_role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    verifier_role_code: Mapped[str] = mapped_column(String(64), nullable=False, default="CAPAVerifier")
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    human_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_summary: Mapped[str | None] = mapped_column(Text)
    linked_finding_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"))
    linked_capa_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("capas.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class IntelligenceActionTask(Base, TimestampMixin):
    __tablename__ = "intelligence_action_tasks"
    __table_args__ = (
        UniqueConstraint("action_plan_id", "sequence"),
        Index("ix_intelligence_action_task_status_due", "status", "due_date"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    action_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intelligence_action_plans.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    owner_role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Open")
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    completion_note: Mapped[str | None] = mapped_column(Text)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntelligenceActionReview(Base, TimestampMixin):
    __tablename__ = "intelligence_action_reviews"
    __table_args__ = (
        Index("ix_intelligence_action_review_plan_type", "action_plan_id", "review_type", "reviewed_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    action_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intelligence_action_plans.id", ondelete="CASCADE"), nullable=False)
    review_type: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IntelligenceConversionRequest(Base, TimestampMixin):
    __tablename__ = "intelligence_conversion_requests"
    __table_args__ = (
        Index("ix_intelligence_conversion_plan_status", "action_plan_id", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    action_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intelligence_action_plans.id", ondelete="CASCADE"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(8))
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Requested")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_entity_id: Mapped[str | None] = mapped_column(String(128))
    execution_note: Mapped[str | None] = mapped_column(Text)


class InstitutionalCommittee(Base, TimestampMixin):
    __tablename__ = "institutional_committees"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        Index("ix_institutional_committee_site_status", "site_id", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    decision_scope: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="Draft")
    chair_role_code: Mapped[str] = mapped_column(String(64), nullable=False, default="AccreditationLead")
    secretary_role_code: Mapped[str] = mapped_column(String(64), nullable=False, default="AccreditationLead")
    quorum_required: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    conflict_policy_reference: Mapped[str] = mapped_column(Text, nullable=False)
    charter_reference: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    activated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommitteeMembership(Base, TimestampMixin):
    __tablename__ = "committee_memberships"
    __table_args__ = (
        UniqueConstraint("committee_id", "member_code"),
        Index("ix_committee_membership_committee_active_role", "committee_id", "active", "role_code"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    committee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutional_committees.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    member_code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    voting_member: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    chair: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    secretary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    authority_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    training_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    term_start: Mapped[date | None] = mapped_column(Date)
    term_end: Mapped[date | None] = mapped_column(Date)
    evidence_reference: Mapped[str | None] = mapped_column(Text)


class SessionGovernance(Base, TimestampMixin):
    __tablename__ = "session_governance"
    __table_args__ = (
        UniqueConstraint("review_session_id"),
        Index("ix_session_governance_committee_status", "committee_id", "status"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    review_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intelligence_review_sessions.id", ondelete="CASCADE"), nullable=False)
    committee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutional_committees.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    expected_voting_members: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attended_voting_members: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quorum_met: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conflicts_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unresolved_conflicts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    authorized_roles: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    evaluation_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    evaluated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommitteeSessionAttendance(Base, TimestampMixin):
    __tablename__ = "committee_session_attendance"
    __table_args__ = (
        UniqueConstraint("governance_id", "membership_id"),
        Index("ix_committee_attendance_governance_attended", "governance_id", "attended", "voting_eligible"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    governance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("session_governance.id", ondelete="CASCADE"), nullable=False)
    membership_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("committee_memberships.id", ondelete="RESTRICT"), nullable=False)
    attended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    voting_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    recused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attendance_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="InPerson")
    signed_reference: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommitteeConflictDeclaration(Base, TimestampMixin):
    __tablename__ = "committee_conflict_declarations"
    __table_args__ = (
        UniqueConstraint("review_item_id", "membership_id"),
        Index("ix_committee_conflict_session_status", "governance_id", "status", "has_conflict"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    governance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("session_governance.id", ondelete="CASCADE"), nullable=False)
    review_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intelligence_review_items.id", ondelete="CASCADE"), nullable=False)
    membership_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("committee_memberships.id", ondelete="RESTRICT"), nullable=False)
    has_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False, default="NoConflict")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="Declared")
    declared_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    declared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_reference: Mapped[str | None] = mapped_column(Text)


class DecisionSlaPolicy(Base, TimestampMixin):
    __tablename__ = "decision_sla_policies"
    __table_args__ = (UniqueConstraint("site_id", "code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    recommendation_to_review_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=72)
    review_to_decision_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    decision_to_plan_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    plan_to_start_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    start_to_completion_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DecisionQualityReview(Base, TimestampMixin):
    __tablename__ = "decision_quality_reviews"
    __table_args__ = (
        UniqueConstraint("review_item_id", "review_type"),
        Index("ix_decision_quality_outcome_score", "outcome", "quality_score"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    review_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intelligence_review_items.id", ondelete="CASCADE"), nullable=False)
    review_type: Mapped[str] = mapped_column(String(32), nullable=False, default="PostDecision")
    rationale_score: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_alignment_score: Mapped[int] = mapped_column(Integer, nullable=False)
    conflict_management_score: Mapped[int] = mapped_column(Integer, nullable=False)
    bias_check_score: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DecisionMetricsSnapshot(Base, TimestampMixin):
    __tablename__ = "decision_metrics_snapshots"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        Index("ix_decision_metrics_site_period", "site_id", "period_start", "period_end"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    decision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    adopted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action_plan_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    median_decision_hours: Mapped[float | None] = mapped_column(Float)
    p90_decision_hours: Mapped[float | None] = mapped_column(Float)
    median_plan_days: Mapped[float | None] = mapped_column(Float)
    sla_breach_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_quality_score: Mapped[float | None] = mapped_column(Float)
    unresolved_conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InstitutionalPilotRun(Base, TimestampMixin):
    __tablename__ = "institutional_pilot_runs"
    __table_args__ = (
        UniqueConstraint("site_id", "code"),
        Index("ix_institutional_pilot_site_status_period", "site_id", "status", "period_start", "period_end"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    pilot_cycle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pilot_cycles.id", ondelete="SET NULL"))
    committee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institutional_committees.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    run_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="Synthetic")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    environment_reference: Mapped[str | None] = mapped_column(Text)
    oidc_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    institutional_data_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class PilotIdentityBinding(Base, TimestampMixin):
    __tablename__ = "pilot_identity_bindings"
    __table_args__ = (
        UniqueConstraint("pilot_run_id", "subject_hash"),
        Index("ix_pilot_identity_run_verified", "pilot_run_id", "verified", "active"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    pilot_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    membership_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("committee_memberships.id", ondelete="SET NULL"))
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    email_hint: Mapped[str | None] = mapped_column(String(320))
    role_codes: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    site_codes: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    authority_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    training_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    site_scope_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_reference: Mapped[str | None] = mapped_column(Text)


class PilotDataSourceAttestation(Base, TimestampMixin):
    __tablename__ = "pilot_data_source_attestations"
    __table_args__ = (
        UniqueConstraint("pilot_run_id", "code"),
        Index("ix_pilot_data_source_run_classification", "pilot_run_id", "data_classification", "attested"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    pilot_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    source_system: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    data_classification: Mapped[str] = mapped_column(String(24), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contains_patient_identifiers: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deidentified_or_tokenized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    attested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PilotSessionExecution(Base, TimestampMixin):
    __tablename__ = "pilot_session_executions"
    __table_args__ = (
        UniqueConstraint("pilot_run_id", "review_session_id"),
        Index("ix_pilot_session_run_status", "pilot_run_id", "status", "sequence"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    pilot_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False)
    review_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intelligence_review_sessions.id", ondelete="RESTRICT"), nullable=False)
    governance_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("session_governance.id", ondelete="SET NULL"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Planned")
    live_data_attested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    governance_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class PilotOutcomeMetric(Base, TimestampMixin):
    __tablename__ = "pilot_outcome_metrics"
    __table_args__ = (
        UniqueConstraint("pilot_run_id", "code"),
        Index("ix_pilot_outcome_run_status_category", "pilot_run_id", "status", "category"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    pilot_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="HigherIsBetter")
    baseline_value: Mapped[float | None] = mapped_column(Float)
    current_value: Mapped[float | None] = mapped_column(Float)
    target_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="NotMeasured")
    source_reference: Mapped[str | None] = mapped_column(Text)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_role_code: Mapped[str] = mapped_column(String(64), nullable=False, default="AccreditationLead")
    guardrail_note: Mapped[str] = mapped_column(Text, nullable=False, default="Outcome metrics do not approve compliance or accreditation readiness.")


class PilotAdoptionEvent(Base, TimestampMixin):
    __tablename__ = "pilot_adoption_events"
    __table_args__ = (Index("ix_pilot_adoption_run_type_time", "pilot_run_id", "event_type", "occurred_at"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    pilot_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    role_code: Mapped[str | None] = mapped_column(String(64))
    actor_token: Mapped[str | None] = mapped_column(String(64))
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class PilotFeedbackRecord(Base, TimestampMixin):
    __tablename__ = "pilot_feedback_records"
    __table_args__ = (Index("ix_pilot_feedback_run_category_rating", "pilot_run_id", "category", "rating"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    pilot_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False)
    respondent_token: Mapped[str] = mapped_column(String(64), nullable=False)
    role_code: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    contains_patient_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="Recorded")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PilotOutcomeReport(Base, TimestampMixin):
    __tablename__ = "pilot_outcome_reports"
    __table_args__ = (
        UniqueConstraint("pilot_run_id", "code"),
        Index("ix_pilot_report_run_status", "pilot_run_id", "status", "generated_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    pilot_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="Draft")
    data_classification: Mapped[str] = mapped_column(String(24), nullable=False)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    conclusions: Mapped[str] = mapped_column(Text, nullable=False)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    file_uri: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    generated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
