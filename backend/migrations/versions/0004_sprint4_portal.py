"""Sprint 4 portal, notifications, exports and OIDC.

Revision ID: 0004_sprint4_portal
Revises: 0003_sprint3_capa_readiness
"""
from alembic import op

revision = "0004_sprint4_portal"
down_revision = "0003_sprint3_capa_readiness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for sql in [
        "CREATE TABLE IF NOT EXISTS notifications (id UUID PRIMARY KEY, site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE, user_id UUID REFERENCES users(id) ON DELETE CASCADE, fingerprint VARCHAR(255) NOT NULL, category VARCHAR(64) NOT NULL, severity VARCHAR(16) NOT NULL DEFAULT 'Info', title VARCHAR(500) NOT NULL, message TEXT NOT NULL, entity_type VARCHAR(128), entity_id VARCHAR(128), action_url TEXT, due_at TIMESTAMPTZ, status VARCHAR(32) NOT NULL DEFAULT 'Unread', read_at TIMESTAMPTZ, archived_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_notification_fingerprint UNIQUE(site_id, fingerprint))",
        "CREATE INDEX IF NOT EXISTS ix_notifications_site_status_created ON notifications (site_id, status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_notifications_severity_due ON notifications (severity, due_at)",
        "CREATE TABLE IF NOT EXISTS export_jobs (id UUID PRIMARY KEY, site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE, requested_by UUID REFERENCES users(id) ON DELETE SET NULL, export_type VARCHAR(64) NOT NULL, file_format VARCHAR(16) NOT NULL, filters JSONB NOT NULL DEFAULT '{}'::jsonb, status VARCHAR(32) NOT NULL DEFAULT 'Queued', file_name VARCHAR(500), storage_uri TEXT, sha256 VARCHAR(64), size_bytes BIGINT, completed_at TIMESTAMPTZ, expires_at TIMESTAMPTZ, error_message TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1)",
        "CREATE INDEX IF NOT EXISTS ix_export_jobs_site_status_created ON export_jobs (site_id, status, created_at)",
    ]:
        op.execute(sql)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS export_jobs")
    op.execute("DROP TABLE IF EXISTS notifications")
