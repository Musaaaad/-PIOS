"""Sprint 7 production operations, SLO, incident, cutover and baseline release.

Revision ID: 0007_sprint7_operations_cutover
Revises: 0006_sprint6_deployment_acceptance
"""
from alembic import op

revision = "0007_sprint7_operations_cutover"
down_revision = "0006_sprint6_deployment_acceptance"
branch_labels = None
depends_on = None


def upgrade():
    for sql in [
        "CREATE TABLE IF NOT EXISTS service_level_objectives (id UUID PRIMARY KEY, site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE, code VARCHAR(64) NOT NULL, name VARCHAR(255) NOT NULL, category VARCHAR(64) NOT NULL, indicator_type VARCHAR(64) NOT NULL, target_operator VARCHAR(8) NOT NULL DEFAULT '>=', target_value DOUBLE PRECISION NOT NULL, unit VARCHAR(32) NOT NULL, window_minutes INTEGER NOT NULL DEFAULT 60, severity_on_breach VARCHAR(8) NOT NULL DEFAULT 'P1', owner_role_code VARCHAR(64) NOT NULL DEFAULT 'SystemAdmin', active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_slo_site_code UNIQUE(site_id,code))",
        "CREATE INDEX IF NOT EXISTS ix_slo_site_active_category ON service_level_objectives(site_id,active,category)",
        "CREATE TABLE IF NOT EXISTS service_level_measurements (id UUID PRIMARY KEY, objective_id UUID NOT NULL REFERENCES service_level_objectives(id) ON DELETE CASCADE, window_start TIMESTAMPTZ NOT NULL, window_end TIMESTAMPTZ NOT NULL, numerator DOUBLE PRECISION, denominator DOUBLE PRECISION, measured_value DOUBLE PRECISION NOT NULL, status VARCHAR(16) NOT NULL DEFAULT 'Pending', source VARCHAR(128) NOT NULL DEFAULT 'Manual', evidence_reference TEXT, details JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_slo_measurement_window UNIQUE(objective_id,window_start,window_end))",
        "CREATE INDEX IF NOT EXISTS ix_slo_measurement_status_window ON service_level_measurements(status,window_end)",
        "CREATE TABLE IF NOT EXISTS operational_incidents (id UUID PRIMARY KEY, site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE, code VARCHAR(64) NOT NULL, title VARCHAR(500) NOT NULL, description TEXT NOT NULL, severity VARCHAR(8) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'Open', category VARCHAR(64) NOT NULL DEFAULT 'Platform', source_type VARCHAR(128), source_id VARCHAR(128), owner_role_code VARCHAR(64) NOT NULL DEFAULT 'SystemAdmin', impact_summary TEXT, root_cause TEXT, resolution_summary TEXT, rollback_required BOOLEAN NOT NULL DEFAULT FALSE, detected_at TIMESTAMPTZ NOT NULL DEFAULT now(), acknowledged_at TIMESTAMPTZ, mitigated_at TIMESTAMPTZ, resolved_at TIMESTAMPTZ, closed_at TIMESTAMPTZ, created_by UUID REFERENCES users(id) ON DELETE SET NULL, closed_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_operational_incident_site_code UNIQUE(site_id,code))",
        "CREATE INDEX IF NOT EXISTS ix_operational_incident_site_status_severity ON operational_incidents(site_id,status,severity)",
        "CREATE TABLE IF NOT EXISTS incident_timeline_entries (id UUID PRIMARY KEY, incident_id UUID NOT NULL REFERENCES operational_incidents(id) ON DELETE CASCADE, event_type VARCHAR(64) NOT NULL, note TEXT NOT NULL, status_from VARCHAR(32), status_to VARCHAR(32), evidence_reference TEXT, actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL, occurred_at TIMESTAMPTZ NOT NULL DEFAULT now())",
        "CREATE INDEX IF NOT EXISTS ix_incident_timeline_incident_time ON incident_timeline_entries(incident_id,occurred_at)",
        "CREATE TABLE IF NOT EXISTS cutover_runs (id UUID PRIMARY KEY, environment_id UUID NOT NULL REFERENCES deployment_environments(id) ON DELETE CASCADE, pilot_cycle_id UUID REFERENCES pilot_cycles(id) ON DELETE SET NULL, code VARCHAR(64) NOT NULL, name VARCHAR(255) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'Draft', decision VARCHAR(32) NOT NULL DEFAULT 'Pending', rationale TEXT, planned_start TIMESTAMPTZ NOT NULL, planned_end TIMESTAMPTZ NOT NULL, actual_start TIMESTAMPTZ, actual_end TIMESTAMPTZ, rollback_triggered BOOLEAN NOT NULL DEFAULT FALSE, summary_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_by UUID REFERENCES users(id) ON DELETE SET NULL, approved_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_cutover_env_code UNIQUE(environment_id,code))",
        "CREATE INDEX IF NOT EXISTS ix_cutover_env_status_start ON cutover_runs(environment_id,status,planned_start)",
        "CREATE TABLE IF NOT EXISTS cutover_tasks (id UUID PRIMARY KEY, cutover_run_id UUID NOT NULL REFERENCES cutover_runs(id) ON DELETE CASCADE, code VARCHAR(64) NOT NULL, phase VARCHAR(64) NOT NULL, sequence INTEGER NOT NULL, title VARCHAR(500) NOT NULL, critical BOOLEAN NOT NULL DEFAULT TRUE, owner_role_code VARCHAR(64) NOT NULL, planned_offset_min INTEGER NOT NULL DEFAULT 0, status VARCHAR(32) NOT NULL DEFAULT 'Pending', evidence_reference TEXT, details TEXT, started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, completed_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_cutover_task_code UNIQUE(cutover_run_id,code))",
        "CREATE INDEX IF NOT EXISTS ix_cutover_task_run_phase_status ON cutover_tasks(cutover_run_id,phase,status)",
        "CREATE TABLE IF NOT EXISTS baseline_releases (id UUID PRIMARY KEY, site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE, snapshot_id UUID NOT NULL REFERENCES readiness_snapshots(id) ON DELETE RESTRICT, code VARCHAR(64) NOT NULL, period_label VARCHAR(64) NOT NULL, classification VARCHAR(32) NOT NULL DEFAULT 'OperationalBaseline', status VARCHAR(32) NOT NULL DEFAULT 'Draft', readiness_score INTEGER, overall_status VARCHAR(64) NOT NULL, critical_open_actions BOOLEAN NOT NULL, esr_status JSONB NOT NULL DEFAULT '{}'::jsonb, details JSONB NOT NULL DEFAULT '{}'::jsonb, release_uri TEXT, release_sha256 VARCHAR(64), approved_by UUID REFERENCES users(id) ON DELETE SET NULL, approved_at TIMESTAMPTZ, published_by UUID REFERENCES users(id) ON DELETE SET NULL, published_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_baseline_release_site_code UNIQUE(site_id,code))",
        "CREATE INDEX IF NOT EXISTS ix_baseline_release_site_status_published ON baseline_releases(site_id,status,published_at)",
    ]:
        op.execute(sql)


def downgrade():
    for table in [
        "baseline_releases", "cutover_tasks", "cutover_runs",
        "incident_timeline_entries", "operational_incidents",
        "service_level_measurements", "service_level_objectives",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
