"""Sprint 5 pilot control, UAT and go-live governance.

Revision ID: 0005_sprint5_pilot
Revises: 0004_sprint4_portal
"""
from alembic import op

revision = "0005_sprint5_pilot"
down_revision = "0004_sprint4_portal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for sql in [
        "CREATE TABLE IF NOT EXISTS pilot_cycles (id UUID PRIMARY KEY, site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE, code VARCHAR(64) NOT NULL, name VARCHAR(255) NOT NULL, objective TEXT NOT NULL, scope_json JSONB NOT NULL DEFAULT '{}'::jsonb, period_start DATE NOT NULL, period_end DATE NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'Draft', owner_role_code VARCHAR(64) NOT NULL DEFAULT 'AccreditationLead', evidence_campaign_id UUID REFERENCES evidence_campaigns(id) ON DELETE SET NULL, activated_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, rollback_reason TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_pilot_site_code UNIQUE(site_id, code))",
        "CREATE INDEX IF NOT EXISTS ix_pilot_site_status_period ON pilot_cycles(site_id,status,period_start,period_end)",
        "CREATE TABLE IF NOT EXISTS pilot_participants (id UUID PRIMARY KEY, pilot_cycle_id UUID NOT NULL REFERENCES pilot_cycles(id) ON DELETE CASCADE, user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, external_subject VARCHAR(255), role_codes JSONB NOT NULL DEFAULT '[]'::jsonb, training_status VARCHAR(32) NOT NULL DEFAULT 'Pending', access_test_status VARCHAR(32) NOT NULL DEFAULT 'Pending', active BOOLEAN NOT NULL DEFAULT TRUE, verified_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_pilot_participant UNIQUE(pilot_cycle_id,user_id))",
        "CREATE INDEX IF NOT EXISTS ix_pilot_participant_status ON pilot_participants(pilot_cycle_id,training_status,access_test_status)",
        "CREATE TABLE IF NOT EXISTS pilot_gate_checks (id UUID PRIMARY KEY, pilot_cycle_id UUID NOT NULL REFERENCES pilot_cycles(id) ON DELETE CASCADE, gate_code VARCHAR(64) NOT NULL, required BOOLEAN NOT NULL DEFAULT TRUE, status VARCHAR(32) NOT NULL DEFAULT 'Pending', evidence_reference TEXT, notes TEXT, checked_by UUID REFERENCES users(id) ON DELETE SET NULL, checked_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_pilot_gate UNIQUE(pilot_cycle_id,gate_code))",
        "CREATE INDEX IF NOT EXISTS ix_pilot_gate_status ON pilot_gate_checks(pilot_cycle_id,required,status)",
        "CREATE TABLE IF NOT EXISTS uat_scenarios (id UUID PRIMARY KEY, code VARCHAR(32) NOT NULL UNIQUE, title_ar VARCHAR(500) NOT NULL, title_en VARCHAR(500) NOT NULL, category VARCHAR(64) NOT NULL, criticality VARCHAR(8) NOT NULL DEFAULT 'P2', steps JSONB NOT NULL DEFAULT '[]'::jsonb, expected_result TEXT NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1)",
        "CREATE TABLE IF NOT EXISTS uat_executions (id UUID PRIMARY KEY, pilot_cycle_id UUID NOT NULL REFERENCES pilot_cycles(id) ON DELETE CASCADE, scenario_id UUID NOT NULL REFERENCES uat_scenarios(id) ON DELETE RESTRICT, attempt INTEGER NOT NULL DEFAULT 1, executor_user_id UUID REFERENCES users(id) ON DELETE SET NULL, status VARCHAR(32) NOT NULL DEFAULT 'NotRun', actual_result TEXT, defect_severity VARCHAR(8), defect_reference VARCHAR(128), evidence_reference TEXT, executed_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1, CONSTRAINT uq_uat_attempt UNIQUE(pilot_cycle_id,scenario_id,attempt))",
        "CREATE INDEX IF NOT EXISTS ix_uat_execution_status ON uat_executions(pilot_cycle_id,status,defect_severity)",
        "CREATE TABLE IF NOT EXISTS pilot_decisions (id UUID PRIMARY KEY, pilot_cycle_id UUID NOT NULL REFERENCES pilot_cycles(id) ON DELETE CASCADE, decision VARCHAR(32) NOT NULL, rationale TEXT NOT NULL, conditions JSONB NOT NULL DEFAULT '[]'::jsonb, decided_by UUID REFERENCES users(id) ON DELETE SET NULL, decided_at TIMESTAMPTZ NOT NULL DEFAULT now(), created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), row_version INTEGER NOT NULL DEFAULT 1)",
        "CREATE INDEX IF NOT EXISTS ix_pilot_decision_cycle_created ON pilot_decisions(pilot_cycle_id,created_at)",
    ]:
        op.execute(sql)


def downgrade() -> None:
    for name in ['pilot_decisions','uat_executions','uat_scenarios','pilot_gate_checks','pilot_participants','pilot_cycles']:
        op.execute(f'DROP TABLE IF EXISTS {name}')
