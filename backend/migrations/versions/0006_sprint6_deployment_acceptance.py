"""Sprint 6 deployment acceptance and institutional runtime controls.

Revision ID: 0006_sprint6_deployment_acceptance
Revises: 0005_sprint5_pilot
"""
from alembic import op
revision="0006_sprint6_deployment_acceptance"
down_revision="0005_sprint5_pilot"
branch_labels=None
depends_on=None

def upgrade():
    for sql in [
        "CREATE TABLE IF NOT EXISTS deployment_environments (id UUID PRIMARY KEY, site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE, code VARCHAR(64) NOT NULL, name VARCHAR(255) NOT NULL, environment_type VARCHAR(32) NOT NULL DEFAULT 'Pilot', status VARCHAR(32) NOT NULL DEFAULT 'Draft', api_base_url TEXT, frontend_base_url TEXT, database_kind VARCHAR(64) NOT NULL DEFAULT 'PostgreSQL', database_version VARCHAR(64), object_storage_kind VARCHAR(64) NOT NULL DEFAULT 'S3', auth_mode VARCHAR(32) NOT NULL DEFAULT 'OIDC', oidc_issuer TEXT, release_version VARCHAR(64) NOT NULL, release_sha VARCHAR(128), tls_enabled BOOLEAN NOT NULL DEFAULT FALSE, monitoring_enabled BOOLEAN NOT NULL DEFAULT FALSE, backup_policy_ref TEXT, active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_deployment_env_site_code UNIQUE(site_id,code))",
        "CREATE INDEX IF NOT EXISTS ix_deployment_env_site_status ON deployment_environments(site_id,status,environment_type)",
        "CREATE TABLE IF NOT EXISTS deployment_acceptance_runs (id UUID PRIMARY KEY, environment_id UUID NOT NULL REFERENCES deployment_environments(id) ON DELETE CASCADE, pilot_cycle_id UUID REFERENCES pilot_cycles(id) ON DELETE SET NULL, run_code VARCHAR(64) NOT NULL, scope VARCHAR(32) NOT NULL DEFAULT 'PreGoLive', status VARCHAR(32) NOT NULL DEFAULT 'Draft', outcome VARCHAR(32) NOT NULL DEFAULT 'NotAssessed', initiated_by UUID REFERENCES users(id) ON DELETE SET NULL, started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, summary_json JSONB NOT NULL DEFAULT '{}'::jsonb, report_uri TEXT, report_sha256 VARCHAR(64), created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_acceptance_run_env_code UNIQUE(environment_id,run_code))",
        "CREATE INDEX IF NOT EXISTS ix_acceptance_run_env_status ON deployment_acceptance_runs(environment_id,status,started_at)",
        "CREATE TABLE IF NOT EXISTS deployment_acceptance_checks (id UUID PRIMARY KEY, run_id UUID NOT NULL REFERENCES deployment_acceptance_runs(id) ON DELETE CASCADE, check_code VARCHAR(64) NOT NULL, category VARCHAR(64) NOT NULL, required BOOLEAN NOT NULL DEFAULT TRUE, execution_mode VARCHAR(32) NOT NULL DEFAULT 'Manual', status VARCHAR(32) NOT NULL DEFAULT 'Pending', expected_value TEXT, measured_value TEXT, evidence_reference TEXT, details TEXT, checked_by UUID REFERENCES users(id) ON DELETE SET NULL, checked_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_acceptance_check UNIQUE(run_id,check_code))",
        "CREATE INDEX IF NOT EXISTS ix_acceptance_check_run_status ON deployment_acceptance_checks(run_id,required,status)",
        "CREATE TABLE IF NOT EXISTS backup_restore_runs (id UUID PRIMARY KEY, environment_id UUID NOT NULL REFERENCES deployment_environments(id) ON DELETE CASCADE, run_code VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'Pending', backup_uri TEXT, backup_sha256 VARCHAR(64), restore_target VARCHAR(255), backup_started_at TIMESTAMPTZ, backup_completed_at TIMESTAMPTZ, restore_started_at TIMESTAMPTZ, restore_completed_at TIMESTAMPTZ, rpo_seconds INTEGER, rto_seconds INTEGER, row_count_summary JSONB NOT NULL DEFAULT '{}'::jsonb, evidence_reference TEXT, executed_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_backup_restore_env_code UNIQUE(environment_id,run_code))",
        "CREATE INDEX IF NOT EXISTS ix_backup_restore_env_status ON backup_restore_runs(environment_id,status,restore_completed_at)",
        "CREATE TABLE IF NOT EXISTS oidc_validation_runs (id UUID PRIMARY KEY, environment_id UUID NOT NULL REFERENCES deployment_environments(id) ON DELETE CASCADE, run_code VARCHAR(64) NOT NULL, issuer TEXT NOT NULL, audience VARCHAR(255) NOT NULL, discovery_url TEXT, jwks_url TEXT, discovery_status VARCHAR(16) NOT NULL DEFAULT 'Pending', jwks_status VARCHAR(16) NOT NULL DEFAULT 'Pending', token_status VARCHAR(16) NOT NULL DEFAULT 'Pending', claims_status VARCHAR(16) NOT NULL DEFAULT 'Pending', required_claims JSONB NOT NULL DEFAULT '[]'::jsonb, observed_claims JSONB NOT NULL DEFAULT '{}'::jsonb, status VARCHAR(32) NOT NULL DEFAULT 'Pending', evidence_reference TEXT, checked_by UUID REFERENCES users(id) ON DELETE SET NULL, checked_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_oidc_validation_env_code UNIQUE(environment_id,run_code))",
        "CREATE INDEX IF NOT EXISTS ix_oidc_validation_env_status ON oidc_validation_runs(environment_id,status,checked_at)",
    ]:
        op.execute(sql)

def downgrade():
    for name in ['oidc_validation_runs','backup_restore_runs','deployment_acceptance_checks','deployment_acceptance_runs','deployment_environments']:
        op.execute(f'DROP TABLE IF EXISTS {name}')
