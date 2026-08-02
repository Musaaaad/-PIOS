"""Sprint 3 findings, CAPA, effectiveness and readiness.

Revision ID: 0003_sprint3_capa_readiness
Revises: 0002_sprint2_evidence
"""
from alembic import op

revision = "0003_sprint3_capa_readiness"
down_revision = "0002_sprint2_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent because a fresh MVP database creates current metadata in 0001.
    for sql in [
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS source_type VARCHAR(32) NOT NULL DEFAULT 'EvidenceReview'",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS owner_role_code VARCHAR(64)",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS due_date DATE",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS closure_comment TEXT",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS closed_by UUID REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS reopened_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE capas ADD COLUMN IF NOT EXISTS title VARCHAR(500) NOT NULL DEFAULT 'Corrective action plan'",
        "ALTER TABLE capas ADD COLUMN IF NOT EXISTS owner_role_code VARCHAR(64)",
        "ALTER TABLE capas ADD COLUMN IF NOT EXISTS verifier_role_code VARCHAR(64)",
        "ALTER TABLE capas ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ",
        "ALTER TABLE capas ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ",
        "ALTER TABLE capas ADD COLUMN IF NOT EXISTS approved_by UUID REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE capas ADD COLUMN IF NOT EXISTS implementation_completed_at TIMESTAMPTZ",
        "ALTER TABLE capas ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ",
        "ALTER TABLE capas ADD COLUMN IF NOT EXISTS closed_by UUID REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE capas ADD COLUMN IF NOT EXISTS closure_comment TEXT",
        "ALTER TABLE capas ADD COLUMN IF NOT EXISTS reopen_reason TEXT",
        "ALTER TABLE capa_actions ADD COLUMN IF NOT EXISTS owner_role_code VARCHAR(64)",
        "ALTER TABLE capa_actions ADD COLUMN IF NOT EXISTS completion_note TEXT",
        "ALTER TABLE capa_actions ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ",
        "ALTER TABLE capa_actions ADD COLUMN IF NOT EXISTS completion_evidence_item_id UUID REFERENCES evidence_items(id) ON DELETE SET NULL",
        "ALTER TABLE effectiveness_checks ADD COLUMN IF NOT EXISTS due_date DATE",
        "ALTER TABLE effectiveness_checks ADD COLUMN IF NOT EXISTS sample_size INTEGER",
        "ALTER TABLE effectiveness_checks ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'Planned'",
        "ALTER TABLE readiness_snapshots ADD COLUMN IF NOT EXISTS applicable_me INTEGER NOT NULL DEFAULT 266",
        "ALTER TABLE readiness_snapshots ADD COLUMN IF NOT EXISTS not_applicable_me INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE readiness_snapshots ADD COLUMN IF NOT EXISTS evidence_partial_me INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE readiness_snapshots ADD COLUMN IF NOT EXISTS evidence_missing_me INTEGER NOT NULL DEFAULT 266",
        "ALTER TABLE readiness_snapshots ADD COLUMN IF NOT EXISTS open_p2 INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE readiness_snapshots ADD COLUMN IF NOT EXISTS critical_open_actions BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE readiness_snapshots ADD COLUMN IF NOT EXISTS overall_status VARCHAR(64) NOT NULL DEFAULT 'NotCalculated'",
        "ALTER TABLE readiness_snapshots ADD COLUMN IF NOT EXISTS details JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE readiness_snapshots ADD COLUMN IF NOT EXISTS calculation_version VARCHAR(32) NOT NULL DEFAULT '1.0'",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_capas_finding_id ON capas (finding_id)",
        "CREATE INDEX IF NOT EXISTS ix_findings_me_status ON findings (measurable_element_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_capas_status_due ON capas (status, due_date)",
        "CREATE INDEX IF NOT EXISTS ix_capa_actions_status_due ON capa_actions (status, due_date)",
        "CREATE INDEX IF NOT EXISTS ix_effectiveness_capa_status_due ON effectiveness_checks (capa_id, status, due_date)",
        "CREATE INDEX IF NOT EXISTS ix_readiness_site_captured ON readiness_snapshots (site_id, captured_at)",
        "CREATE TABLE IF NOT EXISTS readiness_snapshot_items (id UUID PRIMARY KEY, snapshot_id UUID NOT NULL REFERENCES readiness_snapshots(id) ON DELETE CASCADE, measurable_element_id UUID NOT NULL REFERENCES measurable_elements(id) ON DELETE CASCADE, applicability VARCHAR(32) NOT NULL DEFAULT 'Applicable', evidence_status VARCHAR(32) NOT NULL DEFAULT 'Missing', open_findings INTEGER NOT NULL DEFAULT 0, highest_severity VARCHAR(8), readiness_state VARCHAR(64) NOT NULL, rationale TEXT NOT NULL, CONSTRAINT uq_readiness_snapshot_item UNIQUE(snapshot_id, measurable_element_id))",
        "CREATE INDEX IF NOT EXISTS ix_readiness_item_state ON readiness_snapshot_items (readiness_state, highest_severity)",
    ]:
        op.execute(sql)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS readiness_snapshot_items")
    # Column drops are intentionally omitted in the MVP downgrade to avoid destructive loss of audit data.
