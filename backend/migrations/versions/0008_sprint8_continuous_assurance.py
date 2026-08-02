"""Sprint 8 continuous assurance, data quality and cluster rollout.

Revision ID: 0008_sprint8_continuous_assurance
Revises: 0007_sprint7_operations_cutover
"""
from alembic import op

revision = "0008_sprint8_continuous_assurance"
down_revision = "0007_sprint7_operations_cutover"
branch_labels = None
depends_on = None


def upgrade():
    for sql in [
        "CREATE TABLE IF NOT EXISTS assurance_programs (id UUID PRIMARY KEY, site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE, code VARCHAR(64) NOT NULL, name VARCHAR(255) NOT NULL, scope VARCHAR(64) NOT NULL DEFAULT 'P0_ESR', status VARCHAR(32) NOT NULL DEFAULT 'Active', cadence_days INTEGER NOT NULL DEFAULT 90, lookahead_days INTEGER NOT NULL DEFAULT 30, owner_role_code VARCHAR(64) NOT NULL DEFAULT 'AccreditationLead', start_date DATE, end_date DATE, created_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_assurance_program_site_code UNIQUE(site_id,code))",
        "CREATE INDEX IF NOT EXISTS ix_assurance_program_site_status ON assurance_programs(site_id,status)",
        "CREATE TABLE IF NOT EXISTS assurance_controls (id UUID PRIMARY KEY, program_id UUID NOT NULL REFERENCES assurance_programs(id) ON DELETE CASCADE, measurable_element_id UUID NOT NULL REFERENCES measurable_elements(id) ON DELETE RESTRICT, code VARCHAR(64) NOT NULL, title VARCHAR(500) NOT NULL, critical BOOLEAN NOT NULL DEFAULT FALSE, cadence_days INTEGER NOT NULL DEFAULT 90, evidence_types JSONB NOT NULL DEFAULT '[]'::jsonb, owner_role_code VARCHAR(64) NOT NULL DEFAULT 'MEOwner', active BOOLEAN NOT NULL DEFAULT TRUE, last_completed_at TIMESTAMPTZ, next_due_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_assurance_control_program_me UNIQUE(program_id,measurable_element_id))",
        "CREATE INDEX IF NOT EXISTS ix_assurance_control_due_active ON assurance_controls(active,next_due_at)",
        "CREATE TABLE IF NOT EXISTS assurance_cycles (id UUID PRIMARY KEY, program_id UUID NOT NULL REFERENCES assurance_programs(id) ON DELETE CASCADE, code VARCHAR(64) NOT NULL, period_label VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'Open', opened_at TIMESTAMPTZ NOT NULL DEFAULT now(), due_at TIMESTAMPTZ NOT NULL, closed_at TIMESTAMPTZ, summary_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_assurance_cycle_program_code UNIQUE(program_id,code))",
        "CREATE INDEX IF NOT EXISTS ix_assurance_cycle_program_status_due ON assurance_cycles(program_id,status,due_at)",
        "CREATE TABLE IF NOT EXISTS assurance_tasks (id UUID PRIMARY KEY, cycle_id UUID NOT NULL REFERENCES assurance_cycles(id) ON DELETE CASCADE, control_id UUID NOT NULL REFERENCES assurance_controls(id) ON DELETE CASCADE, status VARCHAR(32) NOT NULL DEFAULT 'Pending', due_at TIMESTAMPTZ NOT NULL, result VARCHAR(32), evidence_reference TEXT, comment TEXT, finding_id UUID REFERENCES findings(id) ON DELETE SET NULL, completed_by UUID REFERENCES users(id) ON DELETE SET NULL, completed_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_assurance_task_cycle_control UNIQUE(cycle_id,control_id))",
        "CREATE INDEX IF NOT EXISTS ix_assurance_task_cycle_status_due ON assurance_tasks(cycle_id,status,due_at)",
        "CREATE TABLE IF NOT EXISTS data_quality_rules (id UUID PRIMARY KEY, code VARCHAR(64) NOT NULL UNIQUE, name VARCHAR(255) NOT NULL, category VARCHAR(64) NOT NULL, severity VARCHAR(8) NOT NULL DEFAULT 'P2', owner_role_code VARCHAR(64) NOT NULL DEFAULT 'SystemAdmin', active BOOLEAN NOT NULL DEFAULT TRUE, config JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1)",
        "CREATE TABLE IF NOT EXISTS data_quality_runs (id UUID PRIMARY KEY, site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE, code VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'Running', started_at TIMESTAMPTZ NOT NULL DEFAULT now(), completed_at TIMESTAMPTZ, summary_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_data_quality_run_site_code UNIQUE(site_id,code))",
        "CREATE INDEX IF NOT EXISTS ix_data_quality_run_site_status ON data_quality_runs(site_id,status)",
        "CREATE TABLE IF NOT EXISTS data_quality_issues (id UUID PRIMARY KEY, run_id UUID NOT NULL REFERENCES data_quality_runs(id) ON DELETE CASCADE, rule_id UUID NOT NULL REFERENCES data_quality_rules(id) ON DELETE RESTRICT, entity_type VARCHAR(64) NOT NULL, entity_id VARCHAR(128) NOT NULL, message TEXT NOT NULL, severity VARCHAR(8) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'Open', owner_role_code VARCHAR(64) NOT NULL, evidence_reference TEXT, resolved_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1)",
        "CREATE INDEX IF NOT EXISTS ix_data_quality_issue_run_status_severity ON data_quality_issues(run_id,status,severity)",
        "CREATE TABLE IF NOT EXISTS rollout_waves (id UUID PRIMARY KEY, organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, template_site_id UUID NOT NULL REFERENCES sites(id) ON DELETE RESTRICT, code VARCHAR(64) NOT NULL, name VARCHAR(255) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'Draft', planned_start DATE NOT NULL, planned_end DATE NOT NULL, owner_role_code VARCHAR(64) NOT NULL DEFAULT 'AccreditationLead', summary_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_rollout_wave_org_code UNIQUE(organization_id,code))",
        "CREATE INDEX IF NOT EXISTS ix_rollout_wave_org_status_start ON rollout_waves(organization_id,status,planned_start)",
        "CREATE TABLE IF NOT EXISTS rollout_wave_sites (id UUID PRIMARY KEY, wave_id UUID NOT NULL REFERENCES rollout_waves(id) ON DELETE CASCADE, site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE, status VARCHAR(32) NOT NULL DEFAULT 'Planned', baseline_imported BOOLEAN NOT NULL DEFAULT FALSE, users_ready BOOLEAN NOT NULL DEFAULT FALSE, training_complete BOOLEAN NOT NULL DEFAULT FALSE, deployment_pass BOOLEAN NOT NULL DEFAULT FALSE, oidc_pass BOOLEAN NOT NULL DEFAULT FALSE, go_live_ready BOOLEAN NOT NULL DEFAULT FALSE, gate_status JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_rollout_wave_site UNIQUE(wave_id,site_id))",
        "CREATE INDEX IF NOT EXISTS ix_rollout_wave_site_status_ready ON rollout_wave_sites(wave_id,status,go_live_ready)",
    ]:
        op.execute(sql)


def downgrade():
    for table in [
        "rollout_wave_sites", "rollout_waves", "data_quality_issues", "data_quality_runs",
        "data_quality_rules", "assurance_tasks", "assurance_cycles", "assurance_controls", "assurance_programs",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
