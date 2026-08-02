"""Sprint 2 evidence metadata columns and indexes.

Revision ID: 0002_sprint2_evidence
Revises: 0001_initial
"""
from alembic import op

revision = "0002_sprint2_evidence"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS keeps this safe because the MVP 0001 migration creates the
    # current metadata when a brand-new database is initialized.
    op.execute("ALTER TABLE evidence_campaigns ADD COLUMN IF NOT EXISTS description TEXT")
    op.execute("ALTER TABLE evidence_campaigns ADD COLUMN IF NOT EXISTS opened_at TIMESTAMPTZ")
    op.execute("ALTER TABLE evidence_campaigns ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ")
    op.execute("ALTER TABLE evidence_items ADD COLUMN IF NOT EXISTS structured_data JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE evidence_items ADD COLUMN IF NOT EXISTS sample_size INTEGER")
    op.execute("ALTER TABLE evidence_items ADD COLUMN IF NOT EXISTS collected_at TIMESTAMPTZ")
    op.execute("ALTER TABLE evidence_items ADD COLUMN IF NOT EXISTS collection_location VARCHAR(255)")
    op.execute("ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS scan_status VARCHAR(32) NOT NULL DEFAULT 'Clean'")
    op.execute("ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS scan_message TEXT")
    op.execute("ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()")
    op.execute("CREATE INDEX IF NOT EXISTS ix_campaign_site_status_period ON evidence_campaigns (site_id, status, period_start, period_end)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_evidence_request_campaign_status_due ON evidence_requests (campaign_id, status, due_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_evidence_item_site_status_period ON evidence_items (site_id, status, period_start, period_end)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_evidence_file_scan_status ON evidence_files (scan_status)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_requests_campaign_me_tool ON evidence_requests (campaign_id, measurable_element_id, tool_code)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_files_item_sha256 ON evidence_files (evidence_item_id, sha256)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_evidence_files_item_sha256")
    op.execute("DROP INDEX IF EXISTS uq_evidence_requests_campaign_me_tool")
    op.execute("DROP INDEX IF EXISTS ix_evidence_file_scan_status")
    op.execute("DROP INDEX IF EXISTS ix_evidence_item_site_status_period")
    op.execute("DROP INDEX IF EXISTS ix_evidence_request_campaign_status_due")
    op.execute("DROP INDEX IF EXISTS ix_campaign_site_status_period")
    op.execute("ALTER TABLE evidence_files DROP COLUMN IF EXISTS uploaded_at")
    op.execute("ALTER TABLE evidence_files DROP COLUMN IF EXISTS scan_message")
    op.execute("ALTER TABLE evidence_files DROP COLUMN IF EXISTS scan_status")
    op.execute("ALTER TABLE evidence_items DROP COLUMN IF EXISTS collection_location")
    op.execute("ALTER TABLE evidence_items DROP COLUMN IF EXISTS collected_at")
    op.execute("ALTER TABLE evidence_items DROP COLUMN IF EXISTS sample_size")
    op.execute("ALTER TABLE evidence_items DROP COLUMN IF EXISTS structured_data")
    op.execute("ALTER TABLE evidence_campaigns DROP COLUMN IF EXISTS closed_at")
    op.execute("ALTER TABLE evidence_campaigns DROP COLUMN IF EXISTS opened_at")
    op.execute("ALTER TABLE evidence_campaigns DROP COLUMN IF EXISTS description")
