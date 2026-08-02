"""Sprint 13 institutional pilot execution and outcomes.

Revision ID: 0013_sprint13_institutional_pilot_outcomes
Revises: 0012_sprint12_committee_decision_analytics
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0013_sprint13_institutional_pilot_outcomes"
down_revision = "0012_sprint12_committee_decision_analytics"
branch_labels = None
depends_on = None


def ts():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade():
    op.create_table(
        "institutional_pilot_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("site_id", UUID, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pilot_cycle_id", UUID, sa.ForeignKey("pilot_cycles.id", ondelete="SET NULL")),
        sa.Column("committee_id", UUID, sa.ForeignKey("institutional_committees.id", ondelete="SET NULL")),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("run_mode", sa.String(24), nullable=False, server_default="Synthetic"),
        sa.Column("status", sa.String(32), nullable=False, server_default="Draft"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("environment_reference", sa.Text()),
        sa.Column("oidc_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("institutional_data_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("observation_started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("summary_json", JSONB, nullable=False, server_default="{}"),
        *ts(),
        sa.UniqueConstraint("site_id", "code"),
    )
    op.create_index("ix_institutional_pilot_site_status_period", "institutional_pilot_runs", ["site_id", "status", "period_start", "period_end"])

    op.create_table(
        "pilot_identity_bindings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("pilot_run_id", UUID, sa.ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("membership_id", UUID, sa.ForeignKey("committee_memberships.id", ondelete="SET NULL")),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("email_hint", sa.String(320)),
        sa.Column("role_codes", JSONB, nullable=False, server_default="[]"),
        sa.Column("site_codes", JSONB, nullable=False, server_default="[]"),
        sa.Column("authority_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("training_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("site_scope_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("evidence_reference", sa.Text()),
        *ts(),
        sa.UniqueConstraint("pilot_run_id", "subject_hash"),
    )
    op.create_index("ix_pilot_identity_run_verified", "pilot_identity_bindings", ["pilot_run_id", "verified", "active"])

    op.create_table(
        "pilot_data_source_attestations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("pilot_run_id", UUID, sa.ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("source_system", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("data_classification", sa.String(24), nullable=False),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contains_patient_identifiers", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deidentified_or_tokenized", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("evidence_reference", sa.Text(), nullable=False),
        sa.Column("attested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attested_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("attested_at", sa.DateTime(timezone=True)),
        *ts(),
        sa.UniqueConstraint("pilot_run_id", "code"),
    )
    op.create_index("ix_pilot_data_source_run_classification", "pilot_data_source_attestations", ["pilot_run_id", "data_classification", "attested"])

    op.create_table(
        "pilot_session_executions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("pilot_run_id", UUID, sa.ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_session_id", UUID, sa.ForeignKey("intelligence_review_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("governance_id", UUID, sa.ForeignKey("session_governance.id", ondelete="SET NULL")),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="Planned"),
        sa.Column("live_data_attested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("governance_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("decision_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("evidence_reference", sa.Text()),
        sa.Column("summary_json", JSONB, nullable=False, server_default="{}"),
        *ts(),
        sa.UniqueConstraint("pilot_run_id", "review_session_id"),
    )
    op.create_index("ix_pilot_session_run_status", "pilot_session_executions", ["pilot_run_id", "status", "sequence"])

    op.create_table(
        "pilot_outcome_metrics",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("pilot_run_id", UUID, sa.ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False, server_default="HigherIsBetter"),
        sa.Column("baseline_value", sa.Float()),
        sa.Column("current_value", sa.Float()),
        sa.Column("target_value", sa.Float()),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="NotMeasured"),
        sa.Column("source_reference", sa.Text()),
        sa.Column("measured_at", sa.DateTime(timezone=True)),
        sa.Column("owner_role_code", sa.String(64), nullable=False, server_default="AccreditationLead"),
        sa.Column("guardrail_note", sa.Text(), nullable=False),
        *ts(),
        sa.UniqueConstraint("pilot_run_id", "code"),
    )
    op.create_index("ix_pilot_outcome_run_status_category", "pilot_outcome_metrics", ["pilot_run_id", "status", "category"])

    op.create_table(
        "pilot_adoption_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("pilot_run_id", UUID, sa.ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("role_code", sa.String(64)),
        sa.Column("actor_token", sa.String(64)),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("evidence_reference", sa.Text()),
        sa.Column("metadata_json", JSONB, nullable=False, server_default="{}"),
        *ts(),
    )
    op.create_index("ix_pilot_adoption_run_type_time", "pilot_adoption_events", ["pilot_run_id", "event_type", "occurred_at"])

    op.create_table(
        "pilot_feedback_records",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("pilot_run_id", UUID, sa.ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("respondent_token", sa.String(64), nullable=False),
        sa.Column("role_code", sa.String(64)),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("contains_patient_data", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(24), nullable=False, server_default="Recorded"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *ts(),
    )
    op.create_index("ix_pilot_feedback_run_category_rating", "pilot_feedback_records", ["pilot_run_id", "category", "rating"])

    op.create_table(
        "pilot_outcome_reports",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("pilot_run_id", UUID, sa.ForeignKey("institutional_pilot_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="Draft"),
        sa.Column("data_classification", sa.String(24), nullable=False),
        sa.Column("summary_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("conclusions", sa.Text(), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=False),
        sa.Column("file_uri", sa.Text()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("generated_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("approved_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("published_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        *ts(),
        sa.UniqueConstraint("pilot_run_id", "code"),
    )
    op.create_index("ix_pilot_report_run_status", "pilot_outcome_reports", ["pilot_run_id", "status", "generated_at"])


def downgrade():
    op.drop_index("ix_pilot_report_run_status", table_name="pilot_outcome_reports")
    op.drop_table("pilot_outcome_reports")
    op.drop_index("ix_pilot_feedback_run_category_rating", table_name="pilot_feedback_records")
    op.drop_table("pilot_feedback_records")
    op.drop_index("ix_pilot_adoption_run_type_time", table_name="pilot_adoption_events")
    op.drop_table("pilot_adoption_events")
    op.drop_index("ix_pilot_outcome_run_status_category", table_name="pilot_outcome_metrics")
    op.drop_table("pilot_outcome_metrics")
    op.drop_index("ix_pilot_session_run_status", table_name="pilot_session_executions")
    op.drop_table("pilot_session_executions")
    op.drop_index("ix_pilot_data_source_run_classification", table_name="pilot_data_source_attestations")
    op.drop_table("pilot_data_source_attestations")
    op.drop_index("ix_pilot_identity_run_verified", table_name="pilot_identity_bindings")
    op.drop_table("pilot_identity_bindings")
    op.drop_index("ix_institutional_pilot_site_status_period", table_name="institutional_pilot_runs")
    op.drop_table("institutional_pilot_runs")
