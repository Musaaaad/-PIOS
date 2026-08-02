"""Sprint 12 institutional committee governance and decision analytics.

Revision ID: 0012_sprint12_committee_decision_analytics
Revises: 0011_sprint11_intelligence_to_action
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012_sprint12_committee_decision_analytics"
down_revision = "0011_sprint11_intelligence_to_action"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def ts():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade():
    op.create_table(
        "institutional_committees",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("site_id", UUID, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name_ar", sa.String(255), nullable=False),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("decision_scope", JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(24), nullable=False, server_default="Draft"),
        sa.Column("chair_role_code", sa.String(64), nullable=False, server_default="AccreditationLead"),
        sa.Column("secretary_role_code", sa.String(64), nullable=False, server_default="AccreditationLead"),
        sa.Column("quorum_required", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("conflict_policy_reference", sa.Text(), nullable=False),
        sa.Column("charter_reference", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.Date()),
        sa.Column("effective_to", sa.Date()),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("activated_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        *ts(),
        sa.UniqueConstraint("site_id", "code"),
    )
    op.create_index("ix_institutional_committee_site_status", "institutional_committees", ["site_id", "status"])

    op.create_table(
        "committee_memberships",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("committee_id", UUID, sa.ForeignKey("institutional_committees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("member_code", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("role_code", sa.String(64), nullable=False),
        sa.Column("voting_member", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("chair", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("secretary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("authority_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("training_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("term_start", sa.Date()),
        sa.Column("term_end", sa.Date()),
        sa.Column("evidence_reference", sa.Text()),
        *ts(),
        sa.UniqueConstraint("committee_id", "member_code"),
    )
    op.create_index("ix_committee_membership_committee_active_role", "committee_memberships", ["committee_id", "active", "role_code"])

    op.create_table(
        "session_governance",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("review_session_id", UUID, sa.ForeignKey("intelligence_review_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("committee_id", UUID, sa.ForeignKey("institutional_committees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="Pending"),
        sa.Column("expected_voting_members", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attended_voting_members", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quorum_met", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("conflicts_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("unresolved_conflicts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("authorized_roles", JSONB, nullable=False, server_default="[]"),
        sa.Column("evaluation_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("evaluated_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("evaluated_at", sa.DateTime(timezone=True)),
        *ts(),
        sa.UniqueConstraint("review_session_id"),
    )
    op.create_index("ix_session_governance_committee_status", "session_governance", ["committee_id", "status"])

    op.create_table(
        "committee_session_attendance",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("governance_id", UUID, sa.ForeignKey("session_governance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("membership_id", UUID, sa.ForeignKey("committee_memberships.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("voting_eligible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("recused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attendance_mode", sa.String(24), nullable=False, server_default="InPerson"),
        sa.Column("signed_reference", sa.Text()),
        sa.Column("recorded_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("recorded_at", sa.DateTime(timezone=True)),
        *ts(),
        sa.UniqueConstraint("governance_id", "membership_id"),
    )
    op.create_index("ix_committee_attendance_governance_attended", "committee_session_attendance", ["governance_id", "attended", "voting_eligible"])

    op.create_table(
        "committee_conflict_declarations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("governance_id", UUID, sa.ForeignKey("session_governance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_item_id", UUID, sa.ForeignKey("intelligence_review_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("membership_id", UUID, sa.ForeignKey("committee_memberships.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("has_conflict", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text()),
        sa.Column("disposition", sa.String(32), nullable=False, server_default="NoConflict"),
        sa.Column("status", sa.String(24), nullable=False, server_default="Declared"),
        sa.Column("declared_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("declared_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("evidence_reference", sa.Text()),
        *ts(),
        sa.UniqueConstraint("review_item_id", "membership_id"),
    )
    op.create_index("ix_committee_conflict_session_status", "committee_conflict_declarations", ["governance_id", "status", "has_conflict"])

    op.create_table(
        "decision_sla_policies",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("site_id", UUID, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("recommendation_to_review_hours", sa.Integer(), nullable=False, server_default="72"),
        sa.Column("review_to_decision_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("decision_to_plan_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("plan_to_start_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("start_to_completion_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("approved_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        *ts(),
        sa.UniqueConstraint("site_id", "code"),
    )

    op.create_table(
        "decision_quality_reviews",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("review_item_id", UUID, sa.ForeignKey("intelligence_review_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_type", sa.String(32), nullable=False, server_default="PostDecision"),
        sa.Column("rationale_score", sa.Integer(), nullable=False),
        sa.Column("evidence_score", sa.Integer(), nullable=False),
        sa.Column("policy_alignment_score", sa.Integer(), nullable=False),
        sa.Column("conflict_management_score", sa.Integer(), nullable=False),
        sa.Column("bias_check_score", sa.Integer(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("reviewer_role_code", sa.String(64), nullable=False),
        sa.Column("reviewed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *ts(),
        sa.UniqueConstraint("review_item_id", "review_type"),
    )
    op.create_index("ix_decision_quality_outcome_score", "decision_quality_reviews", ["outcome", "quality_score"])

    op.create_table(
        "decision_metrics_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("site_id", UUID, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decision_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("adopted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_plan_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("median_decision_hours", sa.Float()),
        sa.Column("p90_decision_hours", sa.Float()),
        sa.Column("median_plan_days", sa.Float()),
        sa.Column("sla_breach_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("average_quality_score", sa.Float()),
        sa.Column("unresolved_conflict_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("generated_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *ts(),
        sa.UniqueConstraint("site_id", "code"),
    )
    op.create_index("ix_decision_metrics_site_period", "decision_metrics_snapshots", ["site_id", "period_start", "period_end"])


def downgrade():
    op.drop_index("ix_decision_metrics_site_period", table_name="decision_metrics_snapshots")
    op.drop_table("decision_metrics_snapshots")
    op.drop_index("ix_decision_quality_outcome_score", table_name="decision_quality_reviews")
    op.drop_table("decision_quality_reviews")
    op.drop_table("decision_sla_policies")
    op.drop_index("ix_committee_conflict_session_status", table_name="committee_conflict_declarations")
    op.drop_table("committee_conflict_declarations")
    op.drop_index("ix_committee_attendance_governance_attended", table_name="committee_session_attendance")
    op.drop_table("committee_session_attendance")
    op.drop_index("ix_session_governance_committee_status", table_name="session_governance")
    op.drop_table("session_governance")
    op.drop_index("ix_committee_membership_committee_active_role", table_name="committee_memberships")
    op.drop_table("committee_memberships")
    op.drop_index("ix_institutional_committee_site_status", table_name="institutional_committees")
    op.drop_table("institutional_committees")
