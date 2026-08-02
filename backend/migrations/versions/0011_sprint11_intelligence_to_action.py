"""Sprint 11 intelligence-to-action and human decision governance.

Revision ID: 0011_sprint11_intelligence_to_action
Revises: 0010_sprint10_production_governance
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_sprint11_intelligence_to_action"
down_revision = "0010_sprint10_production_governance"
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
        "intelligence_review_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("site_id", UUID, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="Draft"),
        sa.Column("chair_role_code", sa.String(64), nullable=False, server_default="AccreditationLead"),
        sa.Column("quorum_required", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("notes", sa.Text()),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        *ts(),
        sa.UniqueConstraint("site_id", "code"),
    )
    op.create_index("ix_intelligence_review_site_status_date", "intelligence_review_sessions", ["site_id", "status", "scheduled_at"])

    op.create_table(
        "intelligence_review_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("session_id", UUID, sa.ForeignKey("intelligence_review_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recommendation_id", UUID, sa.ForeignKey("ai_recommendations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="Pending"),
        sa.Column("decision", sa.String(32)),
        sa.Column("rationale", sa.Text()),
        sa.Column("decided_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        *ts(),
        sa.UniqueConstraint("session_id", "recommendation_id"),
        sa.UniqueConstraint("session_id", "sequence"),
    )
    op.create_index("ix_intelligence_review_item_session_status", "intelligence_review_items", ["session_id", "status"])

    op.create_table(
        "intelligence_action_plans",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("site_id", UUID, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recommendation_id", UUID, sa.ForeignKey("ai_recommendations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("measurable_element_id", UUID, sa.ForeignKey("measurable_elements.id", ondelete="SET NULL")),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("owner_role_code", sa.String(64), nullable=False),
        sa.Column("verifier_role_code", sa.String(64), nullable=False, server_default="CAPAVerifier"),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="Draft"),
        sa.Column("human_authorized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("outcome_summary", sa.Text()),
        sa.Column("linked_finding_id", UUID, sa.ForeignKey("findings.id", ondelete="SET NULL")),
        sa.Column("linked_capa_id", UUID, sa.ForeignKey("capas.id", ondelete="SET NULL")),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        *ts(),
        sa.UniqueConstraint("site_id", "code"),
        sa.UniqueConstraint("recommendation_id"),
    )
    op.create_index("ix_intelligence_action_plan_site_status_due", "intelligence_action_plans", ["site_id", "status", "due_date"])

    op.create_table(
        "intelligence_action_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("action_plan_id", UUID, sa.ForeignKey("intelligence_action_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("owner_role_code", sa.String(64), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="Open"),
        sa.Column("evidence_reference", sa.Text()),
        sa.Column("completion_note", sa.Text()),
        sa.Column("completed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *ts(),
        sa.UniqueConstraint("action_plan_id", "sequence"),
    )
    op.create_index("ix_intelligence_action_task_status_due", "intelligence_action_tasks", ["status", "due_date"])

    op.create_table(
        "intelligence_action_reviews",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("action_plan_id", UUID, sa.ForeignKey("intelligence_action_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_type", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("reviewer_role_code", sa.String(64), nullable=False),
        sa.Column("reviewed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *ts(),
    )
    op.create_index("ix_intelligence_action_review_plan_type", "intelligence_action_reviews", ["action_plan_id", "review_type", "reviewed_at"])

    op.create_table(
        "intelligence_conversion_requests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("action_plan_id", UUID, sa.ForeignKey("intelligence_action_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(8)),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="Requested"),
        sa.Column("requested_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("approved_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("executed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("executed_entity_id", sa.String(128)),
        sa.Column("execution_note", sa.Text()),
        *ts(),
    )
    op.create_index("ix_intelligence_conversion_plan_status", "intelligence_conversion_requests", ["action_plan_id", "status"])


def downgrade():
    op.drop_index("ix_intelligence_conversion_plan_status", table_name="intelligence_conversion_requests")
    op.drop_table("intelligence_conversion_requests")
    op.drop_index("ix_intelligence_action_review_plan_type", table_name="intelligence_action_reviews")
    op.drop_table("intelligence_action_reviews")
    op.drop_index("ix_intelligence_action_task_status_due", table_name="intelligence_action_tasks")
    op.drop_table("intelligence_action_tasks")
    op.drop_index("ix_intelligence_action_plan_site_status_due", table_name="intelligence_action_plans")
    op.drop_table("intelligence_action_plans")
    op.drop_index("ix_intelligence_review_item_session_status", table_name="intelligence_review_items")
    op.drop_table("intelligence_review_items")
    op.drop_index("ix_intelligence_review_site_status_date", table_name="intelligence_review_sessions")
    op.drop_table("intelligence_review_sessions")
