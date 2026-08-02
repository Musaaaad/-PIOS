-- PIOS MVP PostgreSQL schema v1.4

CREATE EXTENSION IF NOT EXISTS pgcrypto;


CREATE TABLE data_quality_rules (
	id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	category VARCHAR(64) NOT NULL, 
	severity VARCHAR(8) NOT NULL, 
	owner_role_code VARCHAR(64) NOT NULL, 
	active BOOLEAN NOT NULL, 
	config JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_data_quality_rules PRIMARY KEY (id), 
	CONSTRAINT uq_data_quality_rules_code UNIQUE (code)
);


CREATE TABLE organizations (
	id UUID NOT NULL, 
	code VARCHAR(32) NOT NULL, 
	name_ar VARCHAR(255) NOT NULL, 
	name_en VARCHAR(255) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_organizations PRIMARY KEY (id), 
	CONSTRAINT uq_organizations_code UNIQUE (code)
);


CREATE TABLE roles (
	id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name_ar VARCHAR(255) NOT NULL, 
	description TEXT, 
	CONSTRAINT pk_roles PRIMARY KEY (id), 
	CONSTRAINT uq_roles_code UNIQUE (code)
);


CREATE TABLE standards (
	id UUID NOT NULL, 
	code VARCHAR(16) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	source_version VARCHAR(255) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_standards PRIMARY KEY (id), 
	CONSTRAINT uq_standards_code UNIQUE (code)
);


CREATE TABLE uat_scenarios (
	id UUID NOT NULL, 
	code VARCHAR(32) NOT NULL, 
	title_ar VARCHAR(500) NOT NULL, 
	title_en VARCHAR(500) NOT NULL, 
	category VARCHAR(64) NOT NULL, 
	criticality VARCHAR(8) NOT NULL, 
	steps JSONB NOT NULL, 
	expected_result TEXT NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_uat_scenarios PRIMARY KEY (id), 
	CONSTRAINT uq_uat_scenarios_code UNIQUE (code)
);


CREATE TABLE import_jobs (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	source_name VARCHAR(255) NOT NULL, 
	idempotency_key VARCHAR(128) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	dry_run BOOLEAN NOT NULL, 
	totals JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_import_jobs PRIMARY KEY (id), 
	CONSTRAINT fk_import_jobs_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT uq_import_jobs_idempotency_key UNIQUE (idempotency_key)
);


CREATE TABLE measurable_elements (
	id UUID NOT NULL, 
	me_id VARCHAR(24) NOT NULL, 
	standard_id UUID NOT NULL, 
	official_text TEXT NOT NULL, 
	eoc JSONB NOT NULL, 
	esr BOOLEAN NOT NULL, 
	source_page INTEGER, 
	source_version VARCHAR(255) NOT NULL, 
	owner_role_code VARCHAR(64), 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_measurable_elements PRIMARY KEY (id), 
	CONSTRAINT ck_measurable_elements_me_id_format CHECK (me_id ~ '^MM\.[0-9]+\.[0-9]+$'), 
	CONSTRAINT uq_measurable_elements_me_id UNIQUE (me_id), 
	CONSTRAINT fk_measurable_elements_standard_id_standards FOREIGN KEY(standard_id) REFERENCES standards (id) ON DELETE RESTRICT
);

CREATE INDEX ix_me_standard_esr ON measurable_elements (standard_id, esr);


CREATE TABLE sites (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	code VARCHAR(32) NOT NULL, 
	name_ar VARCHAR(255) NOT NULL, 
	name_en VARCHAR(255) NOT NULL, 
	site_type VARCHAR(64) NOT NULL, 
	timezone VARCHAR(64) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_sites PRIMARY KEY (id), 
	CONSTRAINT uq_sites_organization_id UNIQUE (organization_id, code), 
	CONSTRAINT fk_sites_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE
);


CREATE TABLE users (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	email VARCHAR(320) NOT NULL, 
	display_name VARCHAR(255) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_users PRIMARY KEY (id), 
	CONSTRAINT fk_users_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT uq_users_email UNIQUE (email)
);


CREATE TABLE ai_governance_policies (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	allowed_use_cases JSONB NOT NULL, 
	prohibited_actions JSONB NOT NULL, 
	human_review_required BOOLEAN NOT NULL, 
	model_registry JSONB NOT NULL, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_ai_governance_policies PRIMARY KEY (id), 
	CONSTRAINT uq_ai_governance_policies_organization_id UNIQUE (organization_id, code), 
	CONSTRAINT fk_ai_governance_policies_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_ai_governance_policies_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL
);


CREATE TABLE applicability_decisions (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	measurable_element_id UUID NOT NULL, 
	decision VARCHAR(32) NOT NULL, 
	rationale TEXT NOT NULL, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_applicability_decisions PRIMARY KEY (id), 
	CONSTRAINT uq_applicability_decisions_site_id UNIQUE (site_id, measurable_element_id), 
	CONSTRAINT fk_applicability_decisions_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_applicability_decisions_measurable_element_id_measur_1b05 FOREIGN KEY(measurable_element_id) REFERENCES measurable_elements (id) ON DELETE CASCADE, 
	CONSTRAINT fk_applicability_decisions_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL
);


CREATE TABLE assurance_programs (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	scope VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	cadence_days INTEGER NOT NULL, 
	lookahead_days INTEGER NOT NULL, 
	owner_role_code VARCHAR(64) NOT NULL, 
	start_date DATE, 
	end_date DATE, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_assurance_programs PRIMARY KEY (id), 
	CONSTRAINT uq_assurance_programs_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_assurance_programs_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_assurance_programs_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_assurance_program_site_status ON assurance_programs (site_id, status);


CREATE TABLE audit_events (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	actor_id UUID, 
	action VARCHAR(128) NOT NULL, 
	entity_type VARCHAR(128) NOT NULL, 
	entity_id VARCHAR(128) NOT NULL, 
	before_json JSONB, 
	after_json JSONB, 
	trace_id VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_audit_events PRIMARY KEY (id), 
	CONSTRAINT fk_audit_events_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_audit_events_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_entity_time ON audit_events (entity_type, entity_id, created_at);


CREATE TABLE audit_export_packages (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	period_start TIMESTAMP WITH TIME ZONE NOT NULL, 
	period_end TIMESTAMP WITH TIME ZONE NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	event_count INTEGER NOT NULL, 
	root_hash VARCHAR(64) NOT NULL, 
	file_sha256 VARCHAR(64) NOT NULL, 
	uri TEXT NOT NULL, 
	manifest_json JSONB NOT NULL, 
	created_by UUID, 
	verified_by UUID, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_audit_export_packages PRIMARY KEY (id), 
	CONSTRAINT uq_audit_export_packages_organization_id UNIQUE (organization_id, code), 
	CONSTRAINT fk_audit_export_packages_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_audit_export_packages_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_audit_export_packages_verified_by_users FOREIGN KEY(verified_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_export_org_status_created ON audit_export_packages (organization_id, status, created_at);


CREATE TABLE data_quality_runs (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	summary_json JSONB NOT NULL, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_data_quality_runs PRIMARY KEY (id), 
	CONSTRAINT uq_data_quality_runs_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_data_quality_runs_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_data_quality_runs_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_data_quality_run_site_status ON data_quality_runs (site_id, status);


CREATE TABLE decision_metrics_snapshots (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	period_start TIMESTAMP WITH TIME ZONE NOT NULL, 
	period_end TIMESTAMP WITH TIME ZONE NOT NULL, 
	session_count INTEGER NOT NULL, 
	decision_count INTEGER NOT NULL, 
	adopted_count INTEGER NOT NULL, 
	action_plan_count INTEGER NOT NULL, 
	median_decision_hours FLOAT, 
	p90_decision_hours FLOAT, 
	median_plan_days FLOAT, 
	sla_breach_count INTEGER NOT NULL, 
	average_quality_score FLOAT, 
	unresolved_conflict_count INTEGER NOT NULL, 
	summary_json JSONB NOT NULL, 
	generated_by UUID, 
	generated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_decision_metrics_snapshots PRIMARY KEY (id), 
	CONSTRAINT uq_decision_metrics_snapshots_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_decision_metrics_snapshots_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_decision_metrics_snapshots_generated_by_users FOREIGN KEY(generated_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_decision_metrics_site_period ON decision_metrics_snapshots (site_id, period_start, period_end);


CREATE TABLE decision_sla_policies (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	recommendation_to_review_hours INTEGER NOT NULL, 
	review_to_decision_hours INTEGER NOT NULL, 
	decision_to_plan_days INTEGER NOT NULL, 
	plan_to_start_days INTEGER NOT NULL, 
	start_to_completion_days INTEGER NOT NULL, 
	active BOOLEAN NOT NULL, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_decision_sla_policies PRIMARY KEY (id), 
	CONSTRAINT uq_decision_sla_policies_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_decision_sla_policies_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_decision_sla_policies_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL
);


CREATE TABLE deployment_environments (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	environment_type VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	api_base_url TEXT, 
	frontend_base_url TEXT, 
	database_kind VARCHAR(64) NOT NULL, 
	database_version VARCHAR(64), 
	object_storage_kind VARCHAR(64) NOT NULL, 
	auth_mode VARCHAR(32) NOT NULL, 
	oidc_issuer TEXT, 
	release_version VARCHAR(64) NOT NULL, 
	release_sha VARCHAR(128), 
	tls_enabled BOOLEAN NOT NULL, 
	monitoring_enabled BOOLEAN NOT NULL, 
	backup_policy_ref TEXT, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_deployment_environments PRIMARY KEY (id), 
	CONSTRAINT uq_deployment_environments_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_deployment_environments_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE
);

CREATE INDEX ix_deployment_env_site_status ON deployment_environments (site_id, status, environment_type);


CREATE TABLE documents (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	legacy_evidence_id VARCHAR(32), 
	code VARCHAR(64) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	document_type VARCHAR(128) NOT NULL, 
	lifecycle_status VARCHAR(32) NOT NULL, 
	overlap_family VARCHAR(128), 
	owner_user_id UUID, 
	current_version_id UUID, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_documents PRIMARY KEY (id), 
	CONSTRAINT fk_documents_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT uq_documents_legacy_evidence_id UNIQUE (legacy_evidence_id), 
	CONSTRAINT fk_documents_owner_user_id_users FOREIGN KEY(owner_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_documents_org_code ON documents (organization_id, code);


CREATE TABLE evidence_campaigns (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	description TEXT, 
	period_start DATE NOT NULL, 
	period_end DATE NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	opened_at TIMESTAMP WITH TIME ZONE, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_evidence_campaigns PRIMARY KEY (id), 
	CONSTRAINT fk_evidence_campaigns_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE
);

CREATE INDEX ix_campaign_site_status_period ON evidence_campaigns (site_id, status, period_start, period_end);


CREATE TABLE export_jobs (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	requested_by UUID, 
	export_type VARCHAR(64) NOT NULL, 
	file_format VARCHAR(16) NOT NULL, 
	filters JSONB NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	file_name VARCHAR(500), 
	storage_uri TEXT, 
	sha256 VARCHAR(64), 
	size_bytes BIGINT, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	expires_at TIMESTAMP WITH TIME ZONE, 
	error_message TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_export_jobs PRIMARY KEY (id), 
	CONSTRAINT fk_export_jobs_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_export_jobs_requested_by_users FOREIGN KEY(requested_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_export_jobs_site_status_created ON export_jobs (site_id, status, created_at);


CREATE TABLE import_job_errors (
	id UUID NOT NULL, 
	import_job_id UUID NOT NULL, 
	row_number INTEGER, 
	code VARCHAR(64) NOT NULL, 
	field VARCHAR(128), 
	message TEXT NOT NULL, 
	payload JSONB, 
	CONSTRAINT pk_import_job_errors PRIMARY KEY (id), 
	CONSTRAINT fk_import_job_errors_import_job_id_import_jobs FOREIGN KEY(import_job_id) REFERENCES import_jobs (id) ON DELETE CASCADE
);


CREATE TABLE institutional_committees (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name_ar VARCHAR(255) NOT NULL, 
	name_en VARCHAR(255) NOT NULL, 
	purpose TEXT NOT NULL, 
	decision_scope JSONB NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	chair_role_code VARCHAR(64) NOT NULL, 
	secretary_role_code VARCHAR(64) NOT NULL, 
	quorum_required INTEGER NOT NULL, 
	conflict_policy_reference TEXT NOT NULL, 
	charter_reference TEXT NOT NULL, 
	effective_from DATE, 
	effective_to DATE, 
	created_by UUID, 
	activated_by UUID, 
	activated_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_institutional_committees PRIMARY KEY (id), 
	CONSTRAINT uq_institutional_committees_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_institutional_committees_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_institutional_committees_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_institutional_committees_activated_by_users FOREIGN KEY(activated_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_institutional_committee_site_status ON institutional_committees (site_id, status);


CREATE TABLE intelligence_review_sessions (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	chair_role_code VARCHAR(64) NOT NULL, 
	quorum_required INTEGER NOT NULL, 
	notes TEXT, 
	opened_at TIMESTAMP WITH TIME ZONE, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_intelligence_review_sessions PRIMARY KEY (id), 
	CONSTRAINT uq_intelligence_review_sessions_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_intelligence_review_sessions_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_intelligence_review_sessions_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_intelligence_review_site_status_date ON intelligence_review_sessions (site_id, status, scheduled_at);


CREATE TABLE legal_holds (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	scope_type VARCHAR(64) NOT NULL, 
	scope_id VARCHAR(128), 
	reason TEXT NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	placed_by UUID, 
	placed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	released_by UUID, 
	released_at TIMESTAMP WITH TIME ZONE, 
	release_reason TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_legal_holds PRIMARY KEY (id), 
	CONSTRAINT uq_legal_holds_organization_id UNIQUE (organization_id, code), 
	CONSTRAINT fk_legal_holds_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_legal_holds_placed_by_users FOREIGN KEY(placed_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_legal_holds_released_by_users FOREIGN KEY(released_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_legal_hold_org_status_scope ON legal_holds (organization_id, status, scope_type);


CREATE TABLE nested_clauses (
	id UUID NOT NULL, 
	clause_id VARCHAR(32) NOT NULL, 
	measurable_element_id UUID NOT NULL, 
	ordinal INTEGER NOT NULL, 
	clause_text TEXT, 
	CONSTRAINT pk_nested_clauses PRIMARY KEY (id), 
	CONSTRAINT ck_nested_clauses_clause_id_format CHECK (clause_id ~ '^MM\.[0-9]+\.[0-9]+\.[0-9]+$'), 
	CONSTRAINT uq_nested_clauses_clause_id UNIQUE (clause_id), 
	CONSTRAINT fk_nested_clauses_measurable_element_id_measurable_elements FOREIGN KEY(measurable_element_id) REFERENCES measurable_elements (id) ON DELETE CASCADE
);


CREATE TABLE notifications (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	user_id UUID, 
	fingerprint VARCHAR(255) NOT NULL, 
	category VARCHAR(64) NOT NULL, 
	severity VARCHAR(16) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	message TEXT NOT NULL, 
	entity_type VARCHAR(128), 
	entity_id VARCHAR(128), 
	action_url TEXT, 
	due_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(32) NOT NULL, 
	read_at TIMESTAMP WITH TIME ZONE, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_notifications PRIMARY KEY (id), 
	CONSTRAINT uq_notifications_site_id UNIQUE (site_id, fingerprint), 
	CONSTRAINT fk_notifications_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_notifications_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_notifications_severity_due ON notifications (severity, due_at);

CREATE INDEX ix_notifications_site_status_created ON notifications (site_id, status, created_at);


CREATE TABLE operational_incidents (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	description TEXT NOT NULL, 
	severity VARCHAR(8) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	category VARCHAR(64) NOT NULL, 
	source_type VARCHAR(128), 
	source_id VARCHAR(128), 
	owner_role_code VARCHAR(64) NOT NULL, 
	impact_summary TEXT, 
	root_cause TEXT, 
	resolution_summary TEXT, 
	rollback_required BOOLEAN NOT NULL, 
	detected_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	acknowledged_at TIMESTAMP WITH TIME ZONE, 
	mitigated_at TIMESTAMP WITH TIME ZONE, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	created_by UUID, 
	closed_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_operational_incidents PRIMARY KEY (id), 
	CONSTRAINT uq_operational_incidents_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_operational_incidents_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_operational_incidents_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_operational_incidents_closed_by_users FOREIGN KEY(closed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_operational_incident_site_status_severity ON operational_incidents (site_id, status, severity);


CREATE TABLE portfolio_snapshots (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	period_label VARCHAR(64) NOT NULL, 
	methodology_version VARCHAR(32) NOT NULL, 
	generated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	summary_json JSONB NOT NULL, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_portfolio_snapshots PRIMARY KEY (id), 
	CONSTRAINT uq_portfolio_snapshots_organization_id UNIQUE (organization_id, code), 
	CONSTRAINT fk_portfolio_snapshots_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_portfolio_snapshots_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);


CREATE TABLE readiness_snapshots (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	captured_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	period_label VARCHAR(64) NOT NULL, 
	total_me INTEGER NOT NULL, 
	applicable_me INTEGER NOT NULL, 
	not_applicable_me INTEGER NOT NULL, 
	evidence_sufficient_me INTEGER NOT NULL, 
	evidence_partial_me INTEGER NOT NULL, 
	evidence_missing_me INTEGER NOT NULL, 
	open_p0 INTEGER NOT NULL, 
	open_p1 INTEGER NOT NULL, 
	open_p2 INTEGER NOT NULL, 
	critical_open_actions BOOLEAN NOT NULL, 
	overall_status VARCHAR(64) NOT NULL, 
	esr_status JSONB NOT NULL, 
	details JSONB NOT NULL, 
	calculation_version VARCHAR(32) NOT NULL, 
	readiness_score INTEGER, 
	CONSTRAINT pk_readiness_snapshots PRIMARY KEY (id), 
	CONSTRAINT fk_readiness_snapshots_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE
);

CREATE INDEX ix_readiness_site_captured ON readiness_snapshots (site_id, captured_at);


CREATE TABLE release_packages (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	version VARCHAR(32) NOT NULL, 
	release_sha VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	artifact_count INTEGER NOT NULL, 
	evaluation_json JSONB NOT NULL, 
	created_by UUID, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	published_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_release_packages PRIMARY KEY (id), 
	CONSTRAINT uq_release_packages_organization_id UNIQUE (organization_id, code), 
	CONSTRAINT fk_release_packages_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_release_packages_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_release_packages_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_release_package_org_status_created ON release_packages (organization_id, status, created_at);


CREATE TABLE retention_policies (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	entity_type VARCHAR(128) NOT NULL, 
	retention_days INTEGER NOT NULL, 
	legal_basis TEXT NOT NULL, 
	purge_method VARCHAR(64) NOT NULL, 
	active BOOLEAN NOT NULL, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_retention_policies PRIMARY KEY (id), 
	CONSTRAINT uq_retention_policies_organization_id UNIQUE (organization_id, code), 
	CONSTRAINT fk_retention_policies_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_retention_policies_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL
);


CREATE TABLE risk_assessment_runs (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	period_label VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	methodology_version VARCHAR(32) NOT NULL, 
	generated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	summary_json JSONB NOT NULL, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_risk_assessment_runs PRIMARY KEY (id), 
	CONSTRAINT uq_risk_assessment_runs_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_risk_assessment_runs_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_risk_assessment_runs_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_risk_run_site_generated ON risk_assessment_runs (site_id, generated_at);


CREATE TABLE rollout_waves (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	template_site_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	planned_start DATE NOT NULL, 
	planned_end DATE NOT NULL, 
	owner_role_code VARCHAR(64) NOT NULL, 
	summary_json JSONB NOT NULL, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_rollout_waves PRIMARY KEY (id), 
	CONSTRAINT uq_rollout_waves_organization_id UNIQUE (organization_id, code), 
	CONSTRAINT fk_rollout_waves_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_rollout_waves_template_site_id_sites FOREIGN KEY(template_site_id) REFERENCES sites (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_rollout_waves_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_rollout_wave_org_status_start ON rollout_waves (organization_id, status, planned_start);


CREATE TABLE security_control_assessments (
	id UUID NOT NULL, 
	organization_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	category VARCHAR(64) NOT NULL, 
	severity VARCHAR(8) NOT NULL, 
	required BOOLEAN NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	evidence_reference TEXT, 
	details JSONB NOT NULL, 
	checked_by UUID, 
	checked_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_security_control_assessments PRIMARY KEY (id), 
	CONSTRAINT uq_security_control_assessments_organization_id UNIQUE (organization_id, code), 
	CONSTRAINT fk_security_control_assessments_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_security_control_assessments_checked_by_users FOREIGN KEY(checked_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_security_control_org_status_severity ON security_control_assessments (organization_id, status, severity);


CREATE TABLE service_level_objectives (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	category VARCHAR(64) NOT NULL, 
	indicator_type VARCHAR(64) NOT NULL, 
	target_operator VARCHAR(8) NOT NULL, 
	target_value FLOAT NOT NULL, 
	unit VARCHAR(32) NOT NULL, 
	window_minutes INTEGER NOT NULL, 
	severity_on_breach VARCHAR(8) NOT NULL, 
	owner_role_code VARCHAR(64) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_service_level_objectives PRIMARY KEY (id), 
	CONSTRAINT uq_service_level_objectives_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_service_level_objectives_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE
);

CREATE INDEX ix_slo_site_active_category ON service_level_objectives (site_id, active, category);


CREATE TABLE user_roles (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	role_id UUID NOT NULL, 
	site_id UUID, 
	CONSTRAINT pk_user_roles PRIMARY KEY (id), 
	CONSTRAINT uq_user_roles_user_id UNIQUE (user_id, role_id, site_id), 
	CONSTRAINT fk_user_roles_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	CONSTRAINT fk_user_roles_role_id_roles FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
	CONSTRAINT fk_user_roles_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE
);


CREATE TABLE ai_recommendations (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	risk_run_id UUID, 
	measurable_element_id UUID, 
	recommendation_type VARCHAR(64) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	recommendation_text TEXT NOT NULL, 
	rationale TEXT NOT NULL, 
	confidence FLOAT NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	source_context JSONB NOT NULL, 
	prompt_hash VARCHAR(64) NOT NULL, 
	model_id VARCHAR(128) NOT NULL, 
	guardrail_result JSONB NOT NULL, 
	created_by UUID, 
	reviewed_by UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	decision VARCHAR(32), 
	decision_comment TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_ai_recommendations PRIMARY KEY (id), 
	CONSTRAINT fk_ai_recommendations_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_ai_recommendations_risk_run_id_risk_assessment_runs FOREIGN KEY(risk_run_id) REFERENCES risk_assessment_runs (id) ON DELETE SET NULL, 
	CONSTRAINT fk_ai_recommendations_measurable_element_id_measurable_elements FOREIGN KEY(measurable_element_id) REFERENCES measurable_elements (id) ON DELETE SET NULL, 
	CONSTRAINT fk_ai_recommendations_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_ai_recommendations_reviewed_by_users FOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_ai_recommendation_site_status_created ON ai_recommendations (site_id, status, created_at);


CREATE TABLE assurance_controls (
	id UUID NOT NULL, 
	program_id UUID NOT NULL, 
	measurable_element_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	critical BOOLEAN NOT NULL, 
	cadence_days INTEGER NOT NULL, 
	evidence_types JSONB NOT NULL, 
	owner_role_code VARCHAR(64) NOT NULL, 
	active BOOLEAN NOT NULL, 
	last_completed_at TIMESTAMP WITH TIME ZONE, 
	next_due_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_assurance_controls PRIMARY KEY (id), 
	CONSTRAINT uq_assurance_controls_program_id UNIQUE (program_id, measurable_element_id), 
	CONSTRAINT fk_assurance_controls_program_id_assurance_programs FOREIGN KEY(program_id) REFERENCES assurance_programs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_assurance_controls_measurable_element_id_measurable_elements FOREIGN KEY(measurable_element_id) REFERENCES measurable_elements (id) ON DELETE RESTRICT
);

CREATE INDEX ix_assurance_control_due_active ON assurance_controls (active, next_due_at);


CREATE TABLE assurance_cycles (
	id UUID NOT NULL, 
	program_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	period_label VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	opened_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	due_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	summary_json JSONB NOT NULL, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_assurance_cycles PRIMARY KEY (id), 
	CONSTRAINT uq_assurance_cycles_program_id UNIQUE (program_id, code), 
	CONSTRAINT fk_assurance_cycles_program_id_assurance_programs FOREIGN KEY(program_id) REFERENCES assurance_programs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_assurance_cycles_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_assurance_cycle_program_status_due ON assurance_cycles (program_id, status, due_at);


CREATE TABLE backup_restore_runs (
	id UUID NOT NULL, 
	environment_id UUID NOT NULL, 
	run_code VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	backup_uri TEXT, 
	backup_sha256 VARCHAR(64), 
	restore_target VARCHAR(255), 
	backup_started_at TIMESTAMP WITH TIME ZONE, 
	backup_completed_at TIMESTAMP WITH TIME ZONE, 
	restore_started_at TIMESTAMP WITH TIME ZONE, 
	restore_completed_at TIMESTAMP WITH TIME ZONE, 
	rpo_seconds INTEGER, 
	rto_seconds INTEGER, 
	row_count_summary JSONB NOT NULL, 
	evidence_reference TEXT, 
	executed_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_backup_restore_runs PRIMARY KEY (id), 
	CONSTRAINT uq_backup_restore_runs_environment_id UNIQUE (environment_id, run_code), 
	CONSTRAINT fk_backup_restore_runs_environment_id_deployment_environments FOREIGN KEY(environment_id) REFERENCES deployment_environments (id) ON DELETE CASCADE, 
	CONSTRAINT fk_backup_restore_runs_executed_by_users FOREIGN KEY(executed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_backup_restore_env_status ON backup_restore_runs (environment_id, status, restore_completed_at);


CREATE TABLE baseline_releases (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	snapshot_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	period_label VARCHAR(64) NOT NULL, 
	classification VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	readiness_score INTEGER, 
	overall_status VARCHAR(64) NOT NULL, 
	critical_open_actions BOOLEAN NOT NULL, 
	esr_status JSONB NOT NULL, 
	details JSONB NOT NULL, 
	release_uri TEXT, 
	release_sha256 VARCHAR(64), 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	published_by UUID, 
	published_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_baseline_releases PRIMARY KEY (id), 
	CONSTRAINT uq_baseline_releases_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_baseline_releases_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_baseline_releases_snapshot_id_readiness_snapshots FOREIGN KEY(snapshot_id) REFERENCES readiness_snapshots (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_baseline_releases_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_baseline_releases_published_by_users FOREIGN KEY(published_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_baseline_release_site_status_published ON baseline_releases (site_id, status, published_at);


CREATE TABLE committee_memberships (
	id UUID NOT NULL, 
	committee_id UUID NOT NULL, 
	user_id UUID, 
	member_code VARCHAR(64) NOT NULL, 
	display_name VARCHAR(255) NOT NULL, 
	email VARCHAR(320), 
	role_code VARCHAR(64) NOT NULL, 
	voting_member BOOLEAN NOT NULL, 
	chair BOOLEAN NOT NULL, 
	secretary BOOLEAN NOT NULL, 
	active BOOLEAN NOT NULL, 
	authority_verified BOOLEAN NOT NULL, 
	training_verified BOOLEAN NOT NULL, 
	term_start DATE, 
	term_end DATE, 
	evidence_reference TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_committee_memberships PRIMARY KEY (id), 
	CONSTRAINT uq_committee_memberships_committee_id UNIQUE (committee_id, member_code), 
	CONSTRAINT fk_committee_memberships_committee_id_institutional_committees FOREIGN KEY(committee_id) REFERENCES institutional_committees (id) ON DELETE CASCADE, 
	CONSTRAINT fk_committee_memberships_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_committee_membership_committee_active_role ON committee_memberships (committee_id, active, role_code);


CREATE TABLE data_quality_issues (
	id UUID NOT NULL, 
	run_id UUID NOT NULL, 
	rule_id UUID NOT NULL, 
	entity_type VARCHAR(64) NOT NULL, 
	entity_id VARCHAR(128) NOT NULL, 
	message TEXT NOT NULL, 
	severity VARCHAR(8) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	owner_role_code VARCHAR(64) NOT NULL, 
	evidence_reference TEXT, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_data_quality_issues PRIMARY KEY (id), 
	CONSTRAINT fk_data_quality_issues_run_id_data_quality_runs FOREIGN KEY(run_id) REFERENCES data_quality_runs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_data_quality_issues_rule_id_data_quality_rules FOREIGN KEY(rule_id) REFERENCES data_quality_rules (id) ON DELETE RESTRICT
);

CREATE INDEX ix_data_quality_issue_run_status_severity ON data_quality_issues (run_id, status, severity);


CREATE TABLE document_me_links (
	id UUID NOT NULL, 
	document_id UUID NOT NULL, 
	measurable_element_id UUID NOT NULL, 
	link_type VARCHAR(32) NOT NULL, 
	mandatory BOOLEAN NOT NULL, 
	CONSTRAINT pk_document_me_links PRIMARY KEY (id), 
	CONSTRAINT uq_document_me_links_document_id UNIQUE (document_id, measurable_element_id, link_type), 
	CONSTRAINT fk_document_me_links_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
	CONSTRAINT fk_document_me_links_measurable_element_id_measurable_elements FOREIGN KEY(measurable_element_id) REFERENCES measurable_elements (id) ON DELETE CASCADE
);


CREATE TABLE document_standard_links (
	id UUID NOT NULL, 
	document_id UUID NOT NULL, 
	standard_id UUID NOT NULL, 
	CONSTRAINT pk_document_standard_links PRIMARY KEY (id), 
	CONSTRAINT uq_document_standard_links_document_id UNIQUE (document_id, standard_id), 
	CONSTRAINT fk_document_standard_links_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
	CONSTRAINT fk_document_standard_links_standard_id_standards FOREIGN KEY(standard_id) REFERENCES standards (id) ON DELETE CASCADE
);


CREATE TABLE document_versions (
	id UUID NOT NULL, 
	document_id UUID NOT NULL, 
	version_label VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	effective_date DATE, 
	review_date DATE, 
	source_page_start INTEGER, 
	source_page_end INTEGER, 
	file_uri TEXT, 
	sha256 VARCHAR(64), 
	prepared_by VARCHAR(255), 
	reviewed_by VARCHAR(255), 
	approved_by VARCHAR(255), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_document_versions PRIMARY KEY (id), 
	CONSTRAINT uq_document_versions_document_id UNIQUE (document_id, version_label), 
	CONSTRAINT fk_document_versions_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);


CREATE TABLE evidence_requests (
	id UUID NOT NULL, 
	campaign_id UUID NOT NULL, 
	measurable_element_id UUID NOT NULL, 
	eoc JSONB NOT NULL, 
	tool_code VARCHAR(64) NOT NULL, 
	collector_id UUID, 
	reviewer_id UUID, 
	due_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(32) NOT NULL, 
	instructions TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_evidence_requests PRIMARY KEY (id), 
	CONSTRAINT uq_evidence_requests_campaign_id UNIQUE (campaign_id, measurable_element_id, tool_code), 
	CONSTRAINT fk_evidence_requests_campaign_id_evidence_campaigns FOREIGN KEY(campaign_id) REFERENCES evidence_campaigns (id) ON DELETE CASCADE, 
	CONSTRAINT fk_evidence_requests_measurable_element_id_measurable_elements FOREIGN KEY(measurable_element_id) REFERENCES measurable_elements (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_evidence_requests_collector_id_users FOREIGN KEY(collector_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_evidence_requests_reviewer_id_users FOREIGN KEY(reviewer_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_evidence_request_campaign_status_due ON evidence_requests (campaign_id, status, due_at);


CREATE TABLE incident_timeline_entries (
	id UUID NOT NULL, 
	incident_id UUID NOT NULL, 
	event_type VARCHAR(64) NOT NULL, 
	note TEXT NOT NULL, 
	status_from VARCHAR(32), 
	status_to VARCHAR(32), 
	evidence_reference TEXT, 
	actor_user_id UUID, 
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_incident_timeline_entries PRIMARY KEY (id), 
	CONSTRAINT fk_incident_timeline_entries_incident_id_operational_incidents FOREIGN KEY(incident_id) REFERENCES operational_incidents (id) ON DELETE CASCADE, 
	CONSTRAINT fk_incident_timeline_entries_actor_user_id_users FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_incident_timeline_incident_time ON incident_timeline_entries (incident_id, occurred_at);


CREATE TABLE oidc_validation_runs (
	id UUID NOT NULL, 
	environment_id UUID NOT NULL, 
	run_code VARCHAR(64) NOT NULL, 
	issuer TEXT NOT NULL, 
	audience VARCHAR(255) NOT NULL, 
	discovery_url TEXT, 
	jwks_url TEXT, 
	discovery_status VARCHAR(16) NOT NULL, 
	jwks_status VARCHAR(16) NOT NULL, 
	token_status VARCHAR(16) NOT NULL, 
	claims_status VARCHAR(16) NOT NULL, 
	required_claims JSONB NOT NULL, 
	observed_claims JSONB NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	evidence_reference TEXT, 
	checked_by UUID, 
	checked_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_oidc_validation_runs PRIMARY KEY (id), 
	CONSTRAINT uq_oidc_validation_runs_environment_id UNIQUE (environment_id, run_code), 
	CONSTRAINT fk_oidc_validation_runs_environment_id_deployment_environments FOREIGN KEY(environment_id) REFERENCES deployment_environments (id) ON DELETE CASCADE, 
	CONSTRAINT fk_oidc_validation_runs_checked_by_users FOREIGN KEY(checked_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_oidc_validation_env_status ON oidc_validation_runs (environment_id, status, checked_at);


CREATE TABLE pilot_cycles (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	objective TEXT NOT NULL, 
	scope_json JSONB NOT NULL, 
	period_start DATE NOT NULL, 
	period_end DATE NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	owner_role_code VARCHAR(64) NOT NULL, 
	evidence_campaign_id UUID, 
	activated_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	rollback_reason TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_pilot_cycles PRIMARY KEY (id), 
	CONSTRAINT uq_pilot_cycles_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_pilot_cycles_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_pilot_cycles_evidence_campaign_id_evidence_campaigns FOREIGN KEY(evidence_campaign_id) REFERENCES evidence_campaigns (id) ON DELETE SET NULL
);

CREATE INDEX ix_pilot_site_status_period ON pilot_cycles (site_id, status, period_start, period_end);


CREATE TABLE portfolio_site_metrics (
	id UUID NOT NULL, 
	snapshot_id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	readiness_score INTEGER, 
	risk_score INTEGER, 
	open_p0 INTEGER NOT NULL, 
	open_p1 INTEGER NOT NULL, 
	esr_red INTEGER NOT NULL, 
	data_quality_issues INTEGER NOT NULL, 
	overdue_controls INTEGER NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	details JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_portfolio_site_metrics PRIMARY KEY (id), 
	CONSTRAINT uq_portfolio_site_metrics_snapshot_id UNIQUE (snapshot_id, site_id), 
	CONSTRAINT fk_portfolio_site_metrics_snapshot_id_portfolio_snapshots FOREIGN KEY(snapshot_id) REFERENCES portfolio_snapshots (id) ON DELETE CASCADE, 
	CONSTRAINT fk_portfolio_site_metrics_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE
);

CREATE INDEX ix_portfolio_metric_snapshot_status ON portfolio_site_metrics (snapshot_id, status);


CREATE TABLE readiness_snapshot_items (
	id UUID NOT NULL, 
	snapshot_id UUID NOT NULL, 
	measurable_element_id UUID NOT NULL, 
	applicability VARCHAR(32) NOT NULL, 
	evidence_status VARCHAR(32) NOT NULL, 
	open_findings INTEGER NOT NULL, 
	highest_severity VARCHAR(8), 
	readiness_state VARCHAR(64) NOT NULL, 
	rationale TEXT NOT NULL, 
	CONSTRAINT pk_readiness_snapshot_items PRIMARY KEY (id), 
	CONSTRAINT uq_readiness_snapshot_items_snapshot_id UNIQUE (snapshot_id, measurable_element_id), 
	CONSTRAINT fk_readiness_snapshot_items_snapshot_id_readiness_snapshots FOREIGN KEY(snapshot_id) REFERENCES readiness_snapshots (id) ON DELETE CASCADE, 
	CONSTRAINT fk_readiness_snapshot_items_measurable_element_id_measu_a859 FOREIGN KEY(measurable_element_id) REFERENCES measurable_elements (id) ON DELETE CASCADE
);

CREATE INDEX ix_readiness_item_state ON readiness_snapshot_items (readiness_state, highest_severity);


CREATE TABLE release_artifacts (
	id UUID NOT NULL, 
	release_package_id UUID NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	artifact_type VARCHAR(64) NOT NULL, 
	uri TEXT NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	size_bytes BIGINT NOT NULL, 
	media_type VARCHAR(128), 
	signed BOOLEAN NOT NULL, 
	signature_reference TEXT, 
	immutable BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_release_artifacts PRIMARY KEY (id), 
	CONSTRAINT uq_release_artifacts_release_package_id UNIQUE (release_package_id, name), 
	CONSTRAINT fk_release_artifacts_release_package_id_release_packages FOREIGN KEY(release_package_id) REFERENCES release_packages (id) ON DELETE CASCADE
);

CREATE INDEX ix_release_artifact_package_type ON release_artifacts (release_package_id, artifact_type);


CREATE TABLE risk_assessment_items (
	id UUID NOT NULL, 
	run_id UUID NOT NULL, 
	measurable_element_id UUID NOT NULL, 
	risk_score INTEGER NOT NULL, 
	risk_band VARCHAR(16) NOT NULL, 
	trend VARCHAR(16) NOT NULL, 
	signals JSONB NOT NULL, 
	rationale TEXT NOT NULL, 
	owner_role_code VARCHAR(64), 
	human_status VARCHAR(32) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_risk_assessment_items PRIMARY KEY (id), 
	CONSTRAINT uq_risk_assessment_items_run_id UNIQUE (run_id, measurable_element_id), 
	CONSTRAINT fk_risk_assessment_items_run_id_risk_assessment_runs FOREIGN KEY(run_id) REFERENCES risk_assessment_runs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_risk_assessment_items_measurable_element_id_measurab_5166 FOREIGN KEY(measurable_element_id) REFERENCES measurable_elements (id) ON DELETE RESTRICT
);

CREATE INDEX ix_risk_item_run_band_score ON risk_assessment_items (run_id, risk_band, risk_score);


CREATE TABLE rollout_wave_sites (
	id UUID NOT NULL, 
	wave_id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	baseline_imported BOOLEAN NOT NULL, 
	users_ready BOOLEAN NOT NULL, 
	training_complete BOOLEAN NOT NULL, 
	deployment_pass BOOLEAN NOT NULL, 
	oidc_pass BOOLEAN NOT NULL, 
	go_live_ready BOOLEAN NOT NULL, 
	gate_status JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_rollout_wave_sites PRIMARY KEY (id), 
	CONSTRAINT uq_rollout_wave_sites_wave_id UNIQUE (wave_id, site_id), 
	CONSTRAINT fk_rollout_wave_sites_wave_id_rollout_waves FOREIGN KEY(wave_id) REFERENCES rollout_waves (id) ON DELETE CASCADE, 
	CONSTRAINT fk_rollout_wave_sites_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE
);

CREATE INDEX ix_rollout_wave_site_status_ready ON rollout_wave_sites (wave_id, status, go_live_ready);


CREATE TABLE service_level_measurements (
	id UUID NOT NULL, 
	objective_id UUID NOT NULL, 
	window_start TIMESTAMP WITH TIME ZONE NOT NULL, 
	window_end TIMESTAMP WITH TIME ZONE NOT NULL, 
	numerator FLOAT, 
	denominator FLOAT, 
	measured_value FLOAT NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	source VARCHAR(128) NOT NULL, 
	evidence_reference TEXT, 
	details JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_service_level_measurements PRIMARY KEY (id), 
	CONSTRAINT uq_service_level_measurements_objective_id UNIQUE (objective_id, window_start, window_end), 
	CONSTRAINT fk_service_level_measurements_objective_id_service_leve_3c8c FOREIGN KEY(objective_id) REFERENCES service_level_objectives (id) ON DELETE CASCADE
);

CREATE INDEX ix_slo_measurement_status_window ON service_level_measurements (status, window_end);


CREATE TABLE session_governance (
	id UUID NOT NULL, 
	review_session_id UUID NOT NULL, 
	committee_id UUID NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	expected_voting_members INTEGER NOT NULL, 
	attended_voting_members INTEGER NOT NULL, 
	quorum_met BOOLEAN NOT NULL, 
	conflicts_complete BOOLEAN NOT NULL, 
	unresolved_conflicts INTEGER NOT NULL, 
	authorized_roles JSONB NOT NULL, 
	evaluation_json JSONB NOT NULL, 
	evaluated_by UUID, 
	evaluated_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_session_governance PRIMARY KEY (id), 
	CONSTRAINT uq_session_governance_review_session_id UNIQUE (review_session_id), 
	CONSTRAINT fk_session_governance_review_session_id_intelligence_re_2081 FOREIGN KEY(review_session_id) REFERENCES intelligence_review_sessions (id) ON DELETE CASCADE, 
	CONSTRAINT fk_session_governance_committee_id_institutional_committees FOREIGN KEY(committee_id) REFERENCES institutional_committees (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_session_governance_evaluated_by_users FOREIGN KEY(evaluated_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_session_governance_committee_status ON session_governance (committee_id, status);


CREATE TABLE committee_session_attendance (
	id UUID NOT NULL, 
	governance_id UUID NOT NULL, 
	membership_id UUID NOT NULL, 
	attended BOOLEAN NOT NULL, 
	voting_eligible BOOLEAN NOT NULL, 
	recused BOOLEAN NOT NULL, 
	attendance_mode VARCHAR(24) NOT NULL, 
	signed_reference TEXT, 
	recorded_by UUID, 
	recorded_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_committee_session_attendance PRIMARY KEY (id), 
	CONSTRAINT uq_committee_session_attendance_governance_id UNIQUE (governance_id, membership_id), 
	CONSTRAINT fk_committee_session_attendance_governance_id_session_g_ca65 FOREIGN KEY(governance_id) REFERENCES session_governance (id) ON DELETE CASCADE, 
	CONSTRAINT fk_committee_session_attendance_membership_id_committee_6b12 FOREIGN KEY(membership_id) REFERENCES committee_memberships (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_committee_session_attendance_recorded_by_users FOREIGN KEY(recorded_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_committee_attendance_governance_attended ON committee_session_attendance (governance_id, attended, voting_eligible);


CREATE TABLE cutover_runs (
	id UUID NOT NULL, 
	environment_id UUID NOT NULL, 
	pilot_cycle_id UUID, 
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	decision VARCHAR(32) NOT NULL, 
	rationale TEXT, 
	planned_start TIMESTAMP WITH TIME ZONE NOT NULL, 
	planned_end TIMESTAMP WITH TIME ZONE NOT NULL, 
	actual_start TIMESTAMP WITH TIME ZONE, 
	actual_end TIMESTAMP WITH TIME ZONE, 
	rollback_triggered BOOLEAN NOT NULL, 
	summary_json JSONB NOT NULL, 
	created_by UUID, 
	approved_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_cutover_runs PRIMARY KEY (id), 
	CONSTRAINT uq_cutover_runs_environment_id UNIQUE (environment_id, code), 
	CONSTRAINT fk_cutover_runs_environment_id_deployment_environments FOREIGN KEY(environment_id) REFERENCES deployment_environments (id) ON DELETE CASCADE, 
	CONSTRAINT fk_cutover_runs_pilot_cycle_id_pilot_cycles FOREIGN KEY(pilot_cycle_id) REFERENCES pilot_cycles (id) ON DELETE SET NULL, 
	CONSTRAINT fk_cutover_runs_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_cutover_runs_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_cutover_env_status_start ON cutover_runs (environment_id, status, planned_start);


CREATE TABLE deployment_acceptance_runs (
	id UUID NOT NULL, 
	environment_id UUID NOT NULL, 
	pilot_cycle_id UUID, 
	run_code VARCHAR(64) NOT NULL, 
	scope VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	outcome VARCHAR(32) NOT NULL, 
	initiated_by UUID, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	summary_json JSONB NOT NULL, 
	report_uri TEXT, 
	report_sha256 VARCHAR(64), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_deployment_acceptance_runs PRIMARY KEY (id), 
	CONSTRAINT uq_deployment_acceptance_runs_environment_id UNIQUE (environment_id, run_code), 
	CONSTRAINT fk_deployment_acceptance_runs_environment_id_deployment_1e30 FOREIGN KEY(environment_id) REFERENCES deployment_environments (id) ON DELETE CASCADE, 
	CONSTRAINT fk_deployment_acceptance_runs_pilot_cycle_id_pilot_cycles FOREIGN KEY(pilot_cycle_id) REFERENCES pilot_cycles (id) ON DELETE SET NULL, 
	CONSTRAINT fk_deployment_acceptance_runs_initiated_by_users FOREIGN KEY(initiated_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_acceptance_run_env_status ON deployment_acceptance_runs (environment_id, status, started_at);


CREATE TABLE evidence_items (
	id UUID NOT NULL, 
	request_id UUID, 
	site_id UUID NOT NULL, 
	source_type VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	period_start DATE, 
	period_end DATE, 
	confidentiality VARCHAR(32) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	description TEXT, 
	structured_data JSONB NOT NULL, 
	sample_size INTEGER, 
	collected_at TIMESTAMP WITH TIME ZONE, 
	collection_location VARCHAR(255), 
	submitted_by UUID, 
	submitted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_evidence_items PRIMARY KEY (id), 
	CONSTRAINT fk_evidence_items_request_id_evidence_requests FOREIGN KEY(request_id) REFERENCES evidence_requests (id) ON DELETE SET NULL, 
	CONSTRAINT fk_evidence_items_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_evidence_items_submitted_by_users FOREIGN KEY(submitted_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_evidence_item_site_status_period ON evidence_items (site_id, status, period_start, period_end);


CREATE TABLE institutional_pilot_runs (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	pilot_cycle_id UUID, 
	committee_id UUID, 
	code VARCHAR(64) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	objective TEXT NOT NULL, 
	run_mode VARCHAR(24) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	period_start DATE NOT NULL, 
	period_end DATE NOT NULL, 
	environment_reference TEXT, 
	oidc_required BOOLEAN NOT NULL, 
	institutional_data_required BOOLEAN NOT NULL, 
	activated_at TIMESTAMP WITH TIME ZONE, 
	observation_started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	approved_by UUID, 
	summary_json JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_institutional_pilot_runs PRIMARY KEY (id), 
	CONSTRAINT uq_institutional_pilot_runs_site_id UNIQUE (site_id, code), 
	CONSTRAINT fk_institutional_pilot_runs_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_institutional_pilot_runs_pilot_cycle_id_pilot_cycles FOREIGN KEY(pilot_cycle_id) REFERENCES pilot_cycles (id) ON DELETE SET NULL, 
	CONSTRAINT fk_institutional_pilot_runs_committee_id_institutional__df7f FOREIGN KEY(committee_id) REFERENCES institutional_committees (id) ON DELETE SET NULL, 
	CONSTRAINT fk_institutional_pilot_runs_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_institutional_pilot_site_status_period ON institutional_pilot_runs (site_id, status, period_start, period_end);


CREATE TABLE intelligence_review_items (
	id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	recommendation_id UUID NOT NULL, 
	sequence INTEGER NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	decision VARCHAR(32), 
	rationale TEXT, 
	decided_by UUID, 
	decided_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_intelligence_review_items PRIMARY KEY (id), 
	CONSTRAINT uq_intelligence_review_items_session_id UNIQUE (session_id, recommendation_id), 
	CONSTRAINT uq_intelligence_review_items_session_id UNIQUE (session_id, sequence), 
	CONSTRAINT fk_intelligence_review_items_session_id_intelligence_re_6b61 FOREIGN KEY(session_id) REFERENCES intelligence_review_sessions (id) ON DELETE CASCADE, 
	CONSTRAINT fk_intelligence_review_items_recommendation_id_ai_recom_067e FOREIGN KEY(recommendation_id) REFERENCES ai_recommendations (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_intelligence_review_items_decided_by_users FOREIGN KEY(decided_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_intelligence_review_item_session_status ON intelligence_review_items (session_id, status);


CREATE TABLE pilot_decisions (
	id UUID NOT NULL, 
	pilot_cycle_id UUID NOT NULL, 
	decision VARCHAR(32) NOT NULL, 
	rationale TEXT NOT NULL, 
	conditions JSONB NOT NULL, 
	decided_by UUID, 
	decided_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_pilot_decisions PRIMARY KEY (id), 
	CONSTRAINT fk_pilot_decisions_pilot_cycle_id_pilot_cycles FOREIGN KEY(pilot_cycle_id) REFERENCES pilot_cycles (id) ON DELETE CASCADE, 
	CONSTRAINT fk_pilot_decisions_decided_by_users FOREIGN KEY(decided_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_pilot_decision_cycle_created ON pilot_decisions (pilot_cycle_id, created_at);


CREATE TABLE pilot_gate_checks (
	id UUID NOT NULL, 
	pilot_cycle_id UUID NOT NULL, 
	gate_code VARCHAR(64) NOT NULL, 
	required BOOLEAN NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	evidence_reference TEXT, 
	notes TEXT, 
	checked_by UUID, 
	checked_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_pilot_gate_checks PRIMARY KEY (id), 
	CONSTRAINT uq_pilot_gate_checks_pilot_cycle_id UNIQUE (pilot_cycle_id, gate_code), 
	CONSTRAINT fk_pilot_gate_checks_pilot_cycle_id_pilot_cycles FOREIGN KEY(pilot_cycle_id) REFERENCES pilot_cycles (id) ON DELETE CASCADE, 
	CONSTRAINT fk_pilot_gate_checks_checked_by_users FOREIGN KEY(checked_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_pilot_gate_status ON pilot_gate_checks (pilot_cycle_id, required, status);


CREATE TABLE pilot_participants (
	id UUID NOT NULL, 
	pilot_cycle_id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	external_subject VARCHAR(255), 
	role_codes JSONB NOT NULL, 
	training_status VARCHAR(32) NOT NULL, 
	access_test_status VARCHAR(32) NOT NULL, 
	active BOOLEAN NOT NULL, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_pilot_participants PRIMARY KEY (id), 
	CONSTRAINT uq_pilot_participants_pilot_cycle_id UNIQUE (pilot_cycle_id, user_id), 
	CONSTRAINT fk_pilot_participants_pilot_cycle_id_pilot_cycles FOREIGN KEY(pilot_cycle_id) REFERENCES pilot_cycles (id) ON DELETE CASCADE, 
	CONSTRAINT fk_pilot_participants_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_pilot_participant_status ON pilot_participants (pilot_cycle_id, training_status, access_test_status);


CREATE TABLE uat_executions (
	id UUID NOT NULL, 
	pilot_cycle_id UUID NOT NULL, 
	scenario_id UUID NOT NULL, 
	attempt INTEGER NOT NULL, 
	executor_user_id UUID, 
	status VARCHAR(32) NOT NULL, 
	actual_result TEXT, 
	defect_severity VARCHAR(8), 
	defect_reference VARCHAR(128), 
	evidence_reference TEXT, 
	executed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_uat_executions PRIMARY KEY (id), 
	CONSTRAINT uq_uat_executions_pilot_cycle_id UNIQUE (pilot_cycle_id, scenario_id, attempt), 
	CONSTRAINT fk_uat_executions_pilot_cycle_id_pilot_cycles FOREIGN KEY(pilot_cycle_id) REFERENCES pilot_cycles (id) ON DELETE CASCADE, 
	CONSTRAINT fk_uat_executions_scenario_id_uat_scenarios FOREIGN KEY(scenario_id) REFERENCES uat_scenarios (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_uat_executions_executor_user_id_users FOREIGN KEY(executor_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_uat_execution_status ON uat_executions (pilot_cycle_id, status, defect_severity);


CREATE TABLE committee_conflict_declarations (
	id UUID NOT NULL, 
	governance_id UUID NOT NULL, 
	review_item_id UUID NOT NULL, 
	membership_id UUID NOT NULL, 
	has_conflict BOOLEAN NOT NULL, 
	description TEXT, 
	disposition VARCHAR(32) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	declared_by UUID, 
	declared_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	resolved_by UUID, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	evidence_reference TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_committee_conflict_declarations PRIMARY KEY (id), 
	CONSTRAINT uq_committee_conflict_declarations_review_item_id UNIQUE (review_item_id, membership_id), 
	CONSTRAINT fk_committee_conflict_declarations_governance_id_sessio_8b41 FOREIGN KEY(governance_id) REFERENCES session_governance (id) ON DELETE CASCADE, 
	CONSTRAINT fk_committee_conflict_declarations_review_item_id_intel_55ce FOREIGN KEY(review_item_id) REFERENCES intelligence_review_items (id) ON DELETE CASCADE, 
	CONSTRAINT fk_committee_conflict_declarations_membership_id_commit_c8ea FOREIGN KEY(membership_id) REFERENCES committee_memberships (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_committee_conflict_declarations_declared_by_users FOREIGN KEY(declared_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_committee_conflict_declarations_resolved_by_users FOREIGN KEY(resolved_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_committee_conflict_session_status ON committee_conflict_declarations (governance_id, status, has_conflict);


CREATE TABLE cutover_tasks (
	id UUID NOT NULL, 
	cutover_run_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	phase VARCHAR(64) NOT NULL, 
	sequence INTEGER NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	critical BOOLEAN NOT NULL, 
	owner_role_code VARCHAR(64) NOT NULL, 
	planned_offset_min INTEGER NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	evidence_reference TEXT, 
	details TEXT, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	completed_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_cutover_tasks PRIMARY KEY (id), 
	CONSTRAINT uq_cutover_tasks_cutover_run_id UNIQUE (cutover_run_id, code), 
	CONSTRAINT fk_cutover_tasks_cutover_run_id_cutover_runs FOREIGN KEY(cutover_run_id) REFERENCES cutover_runs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_cutover_tasks_completed_by_users FOREIGN KEY(completed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_cutover_task_run_phase_status ON cutover_tasks (cutover_run_id, phase, status);


CREATE TABLE decision_quality_reviews (
	id UUID NOT NULL, 
	review_item_id UUID NOT NULL, 
	review_type VARCHAR(32) NOT NULL, 
	rationale_score INTEGER NOT NULL, 
	evidence_score INTEGER NOT NULL, 
	policy_alignment_score INTEGER NOT NULL, 
	conflict_management_score INTEGER NOT NULL, 
	bias_check_score INTEGER NOT NULL, 
	quality_score FLOAT NOT NULL, 
	outcome VARCHAR(24) NOT NULL, 
	comment TEXT NOT NULL, 
	reviewer_role_code VARCHAR(64) NOT NULL, 
	reviewed_by UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_decision_quality_reviews PRIMARY KEY (id), 
	CONSTRAINT uq_decision_quality_reviews_review_item_id UNIQUE (review_item_id, review_type), 
	CONSTRAINT fk_decision_quality_reviews_review_item_id_intelligence_be35 FOREIGN KEY(review_item_id) REFERENCES intelligence_review_items (id) ON DELETE CASCADE, 
	CONSTRAINT fk_decision_quality_reviews_reviewed_by_users FOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_decision_quality_outcome_score ON decision_quality_reviews (outcome, quality_score);


CREATE TABLE deployment_acceptance_checks (
	id UUID NOT NULL, 
	run_id UUID NOT NULL, 
	check_code VARCHAR(64) NOT NULL, 
	category VARCHAR(64) NOT NULL, 
	required BOOLEAN NOT NULL, 
	execution_mode VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	expected_value TEXT, 
	measured_value TEXT, 
	evidence_reference TEXT, 
	details TEXT, 
	checked_by UUID, 
	checked_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_deployment_acceptance_checks PRIMARY KEY (id), 
	CONSTRAINT uq_deployment_acceptance_checks_run_id UNIQUE (run_id, check_code), 
	CONSTRAINT fk_deployment_acceptance_checks_run_id_deployment_accep_6d06 FOREIGN KEY(run_id) REFERENCES deployment_acceptance_runs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_deployment_acceptance_checks_checked_by_users FOREIGN KEY(checked_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_acceptance_check_run_status ON deployment_acceptance_checks (run_id, required, status);


CREATE TABLE evidence_files (
	id UUID NOT NULL, 
	evidence_item_id UUID NOT NULL, 
	file_name VARCHAR(500) NOT NULL, 
	content_type VARCHAR(128) NOT NULL, 
	size_bytes BIGINT NOT NULL, 
	storage_uri TEXT NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	scan_status VARCHAR(32) NOT NULL, 
	scan_message TEXT, 
	uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_evidence_files PRIMARY KEY (id), 
	CONSTRAINT uq_evidence_files_evidence_item_id UNIQUE (evidence_item_id, sha256), 
	CONSTRAINT fk_evidence_files_evidence_item_id_evidence_items FOREIGN KEY(evidence_item_id) REFERENCES evidence_items (id) ON DELETE CASCADE
);

CREATE INDEX ix_evidence_file_scan_status ON evidence_files (scan_status);


CREATE TABLE evidence_me_links (
	id UUID NOT NULL, 
	evidence_item_id UUID NOT NULL, 
	measurable_element_id UUID NOT NULL, 
	coverage_type VARCHAR(32) NOT NULL, 
	scope_sites JSONB NOT NULL, 
	scope_shifts JSONB NOT NULL, 
	CONSTRAINT pk_evidence_me_links PRIMARY KEY (id), 
	CONSTRAINT uq_evidence_me_links_evidence_item_id UNIQUE (evidence_item_id, measurable_element_id), 
	CONSTRAINT fk_evidence_me_links_evidence_item_id_evidence_items FOREIGN KEY(evidence_item_id) REFERENCES evidence_items (id) ON DELETE CASCADE, 
	CONSTRAINT fk_evidence_me_links_measurable_element_id_measurable_elements FOREIGN KEY(measurable_element_id) REFERENCES measurable_elements (id) ON DELETE CASCADE
);


CREATE TABLE evidence_reviews (
	id UUID NOT NULL, 
	evidence_item_id UUID NOT NULL, 
	reviewer_id UUID, 
	verdict VARCHAR(32) NOT NULL, 
	reason_code VARCHAR(64) NOT NULL, 
	comment TEXT, 
	reviewed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_evidence_reviews PRIMARY KEY (id), 
	CONSTRAINT fk_evidence_reviews_evidence_item_id_evidence_items FOREIGN KEY(evidence_item_id) REFERENCES evidence_items (id) ON DELETE CASCADE, 
	CONSTRAINT fk_evidence_reviews_reviewer_id_users FOREIGN KEY(reviewer_id) REFERENCES users (id) ON DELETE SET NULL
);


CREATE TABLE findings (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	measurable_element_id UUID NOT NULL, 
	evidence_item_id UUID, 
	source_type VARCHAR(32) NOT NULL, 
	criterion VARCHAR(500) NOT NULL, 
	severity VARCHAR(8) NOT NULL, 
	problem_statement TEXT NOT NULL, 
	owner_role_code VARCHAR(64), 
	due_date DATE, 
	status VARCHAR(32) NOT NULL, 
	acknowledged_at TIMESTAMP WITH TIME ZONE, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	closure_comment TEXT, 
	closed_by UUID, 
	reopened_count INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_findings PRIMARY KEY (id), 
	CONSTRAINT fk_findings_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_findings_measurable_element_id_measurable_elements FOREIGN KEY(measurable_element_id) REFERENCES measurable_elements (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_findings_evidence_item_id_evidence_items FOREIGN KEY(evidence_item_id) REFERENCES evidence_items (id) ON DELETE SET NULL, 
	CONSTRAINT fk_findings_closed_by_users FOREIGN KEY(closed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_findings_site_severity_status ON findings (site_id, severity, status);

CREATE INDEX ix_findings_me_status ON findings (measurable_element_id, status);


CREATE TABLE pilot_adoption_events (
	id UUID NOT NULL, 
	pilot_run_id UUID NOT NULL, 
	event_type VARCHAR(64) NOT NULL, 
	role_code VARCHAR(64), 
	actor_token VARCHAR(64), 
	event_count INTEGER NOT NULL, 
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	evidence_reference TEXT, 
	metadata_json JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_pilot_adoption_events PRIMARY KEY (id), 
	CONSTRAINT fk_pilot_adoption_events_pilot_run_id_institutional_pilot_runs FOREIGN KEY(pilot_run_id) REFERENCES institutional_pilot_runs (id) ON DELETE CASCADE
);

CREATE INDEX ix_pilot_adoption_run_type_time ON pilot_adoption_events (pilot_run_id, event_type, occurred_at);


CREATE TABLE pilot_data_source_attestations (
	id UUID NOT NULL, 
	pilot_run_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	source_system VARCHAR(255) NOT NULL, 
	source_type VARCHAR(64) NOT NULL, 
	data_classification VARCHAR(24) NOT NULL, 
	period_start DATE, 
	period_end DATE, 
	record_count INTEGER NOT NULL, 
	contains_patient_identifiers BOOLEAN NOT NULL, 
	deidentified_or_tokenized BOOLEAN NOT NULL, 
	checksum_sha256 VARCHAR(64), 
	evidence_reference TEXT NOT NULL, 
	attested BOOLEAN NOT NULL, 
	attested_by UUID, 
	attested_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_pilot_data_source_attestations PRIMARY KEY (id), 
	CONSTRAINT uq_pilot_data_source_attestations_pilot_run_id UNIQUE (pilot_run_id, code), 
	CONSTRAINT fk_pilot_data_source_attestations_pilot_run_id_institut_3fdc FOREIGN KEY(pilot_run_id) REFERENCES institutional_pilot_runs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_pilot_data_source_attestations_attested_by_users FOREIGN KEY(attested_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_pilot_data_source_run_classification ON pilot_data_source_attestations (pilot_run_id, data_classification, attested);


CREATE TABLE pilot_feedback_records (
	id UUID NOT NULL, 
	pilot_run_id UUID NOT NULL, 
	respondent_token VARCHAR(64) NOT NULL, 
	role_code VARCHAR(64), 
	category VARCHAR(64) NOT NULL, 
	rating INTEGER NOT NULL, 
	comment TEXT, 
	contains_patient_data BOOLEAN NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	recorded_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_pilot_feedback_records PRIMARY KEY (id), 
	CONSTRAINT fk_pilot_feedback_records_pilot_run_id_institutional_pilot_runs FOREIGN KEY(pilot_run_id) REFERENCES institutional_pilot_runs (id) ON DELETE CASCADE
);

CREATE INDEX ix_pilot_feedback_run_category_rating ON pilot_feedback_records (pilot_run_id, category, rating);


CREATE TABLE pilot_identity_bindings (
	id UUID NOT NULL, 
	pilot_run_id UUID NOT NULL, 
	user_id UUID, 
	membership_id UUID, 
	issuer TEXT NOT NULL, 
	subject_hash VARCHAR(64) NOT NULL, 
	email_hint VARCHAR(320), 
	role_codes JSONB NOT NULL, 
	site_codes JSONB NOT NULL, 
	authority_verified BOOLEAN NOT NULL, 
	training_verified BOOLEAN NOT NULL, 
	site_scope_verified BOOLEAN NOT NULL, 
	verified BOOLEAN NOT NULL, 
	active BOOLEAN NOT NULL, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	evidence_reference TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_pilot_identity_bindings PRIMARY KEY (id), 
	CONSTRAINT uq_pilot_identity_bindings_pilot_run_id UNIQUE (pilot_run_id, subject_hash), 
	CONSTRAINT fk_pilot_identity_bindings_pilot_run_id_institutional_p_9490 FOREIGN KEY(pilot_run_id) REFERENCES institutional_pilot_runs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_pilot_identity_bindings_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_pilot_identity_bindings_membership_id_committee_memberships FOREIGN KEY(membership_id) REFERENCES committee_memberships (id) ON DELETE SET NULL
);

CREATE INDEX ix_pilot_identity_run_verified ON pilot_identity_bindings (pilot_run_id, verified, active);


CREATE TABLE pilot_outcome_metrics (
	id UUID NOT NULL, 
	pilot_run_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	category VARCHAR(64) NOT NULL, 
	direction VARCHAR(16) NOT NULL, 
	baseline_value FLOAT, 
	current_value FLOAT, 
	target_value FLOAT, 
	unit VARCHAR(32) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	source_reference TEXT, 
	measured_at TIMESTAMP WITH TIME ZONE, 
	owner_role_code VARCHAR(64) NOT NULL, 
	guardrail_note TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_pilot_outcome_metrics PRIMARY KEY (id), 
	CONSTRAINT uq_pilot_outcome_metrics_pilot_run_id UNIQUE (pilot_run_id, code), 
	CONSTRAINT fk_pilot_outcome_metrics_pilot_run_id_institutional_pilot_runs FOREIGN KEY(pilot_run_id) REFERENCES institutional_pilot_runs (id) ON DELETE CASCADE
);

CREATE INDEX ix_pilot_outcome_run_status_category ON pilot_outcome_metrics (pilot_run_id, status, category);


CREATE TABLE pilot_outcome_reports (
	id UUID NOT NULL, 
	pilot_run_id UUID NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	data_classification VARCHAR(24) NOT NULL, 
	summary_json JSONB NOT NULL, 
	conclusions TEXT NOT NULL, 
	limitations TEXT NOT NULL, 
	file_uri TEXT, 
	sha256 VARCHAR(64), 
	generated_by UUID, 
	generated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	published_by UUID, 
	published_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_pilot_outcome_reports PRIMARY KEY (id), 
	CONSTRAINT uq_pilot_outcome_reports_pilot_run_id UNIQUE (pilot_run_id, code), 
	CONSTRAINT fk_pilot_outcome_reports_pilot_run_id_institutional_pilot_runs FOREIGN KEY(pilot_run_id) REFERENCES institutional_pilot_runs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_pilot_outcome_reports_generated_by_users FOREIGN KEY(generated_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_pilot_outcome_reports_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_pilot_outcome_reports_published_by_users FOREIGN KEY(published_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_pilot_report_run_status ON pilot_outcome_reports (pilot_run_id, status, generated_at);


CREATE TABLE pilot_session_executions (
	id UUID NOT NULL, 
	pilot_run_id UUID NOT NULL, 
	review_session_id UUID NOT NULL, 
	governance_id UUID, 
	sequence INTEGER NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	live_data_attested BOOLEAN NOT NULL, 
	governance_ready BOOLEAN NOT NULL, 
	decision_count INTEGER NOT NULL, 
	quality_review_count INTEGER NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	evidence_reference TEXT, 
	summary_json JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_pilot_session_executions PRIMARY KEY (id), 
	CONSTRAINT uq_pilot_session_executions_pilot_run_id UNIQUE (pilot_run_id, review_session_id), 
	CONSTRAINT fk_pilot_session_executions_pilot_run_id_institutional__0dbd FOREIGN KEY(pilot_run_id) REFERENCES institutional_pilot_runs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_pilot_session_executions_review_session_id_intellige_fb65 FOREIGN KEY(review_session_id) REFERENCES intelligence_review_sessions (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_pilot_session_executions_governance_id_session_governance FOREIGN KEY(governance_id) REFERENCES session_governance (id) ON DELETE SET NULL
);

CREATE INDEX ix_pilot_session_run_status ON pilot_session_executions (pilot_run_id, status, sequence);


CREATE TABLE assurance_tasks (
	id UUID NOT NULL, 
	cycle_id UUID NOT NULL, 
	control_id UUID NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	due_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	result VARCHAR(32), 
	evidence_reference TEXT, 
	comment TEXT, 
	finding_id UUID, 
	completed_by UUID, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_assurance_tasks PRIMARY KEY (id), 
	CONSTRAINT uq_assurance_tasks_cycle_id UNIQUE (cycle_id, control_id), 
	CONSTRAINT fk_assurance_tasks_cycle_id_assurance_cycles FOREIGN KEY(cycle_id) REFERENCES assurance_cycles (id) ON DELETE CASCADE, 
	CONSTRAINT fk_assurance_tasks_control_id_assurance_controls FOREIGN KEY(control_id) REFERENCES assurance_controls (id) ON DELETE CASCADE, 
	CONSTRAINT fk_assurance_tasks_finding_id_findings FOREIGN KEY(finding_id) REFERENCES findings (id) ON DELETE SET NULL, 
	CONSTRAINT fk_assurance_tasks_completed_by_users FOREIGN KEY(completed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_assurance_task_cycle_status_due ON assurance_tasks (cycle_id, status, due_at);


CREATE TABLE capas (
	id UUID NOT NULL, 
	finding_id UUID NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	owner_id UUID, 
	owner_role_code VARCHAR(64), 
	verifier_role_code VARCHAR(64), 
	due_date DATE, 
	status VARCHAR(32) NOT NULL, 
	root_cause TEXT, 
	action_plan TEXT NOT NULL, 
	submitted_at TIMESTAMP WITH TIME ZONE, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	approved_by UUID, 
	implementation_completed_at TIMESTAMP WITH TIME ZONE, 
	closed_at TIMESTAMP WITH TIME ZONE, 
	closed_by UUID, 
	closure_comment TEXT, 
	reopen_reason TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_capas PRIMARY KEY (id), 
	CONSTRAINT uq_capas_finding_id UNIQUE (finding_id), 
	CONSTRAINT fk_capas_finding_id_findings FOREIGN KEY(finding_id) REFERENCES findings (id) ON DELETE CASCADE, 
	CONSTRAINT fk_capas_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_capas_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_capas_closed_by_users FOREIGN KEY(closed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_capas_status_due ON capas (status, due_date);


CREATE TABLE evidence_review_tests (
	id UUID NOT NULL, 
	review_id UUID NOT NULL, 
	test_code VARCHAR(64) NOT NULL, 
	result VARCHAR(16) NOT NULL, 
	comment TEXT, 
	CONSTRAINT pk_evidence_review_tests PRIMARY KEY (id), 
	CONSTRAINT uq_evidence_review_tests_review_id UNIQUE (review_id, test_code), 
	CONSTRAINT fk_evidence_review_tests_review_id_evidence_reviews FOREIGN KEY(review_id) REFERENCES evidence_reviews (id) ON DELETE CASCADE
);


CREATE TABLE capa_actions (
	id UUID NOT NULL, 
	capa_id UUID NOT NULL, 
	sequence INTEGER NOT NULL, 
	action TEXT NOT NULL, 
	owner_id UUID, 
	owner_role_code VARCHAR(64), 
	due_date DATE, 
	status VARCHAR(32) NOT NULL, 
	completion_note TEXT, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	completion_evidence_item_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_capa_actions PRIMARY KEY (id), 
	CONSTRAINT uq_capa_actions_capa_id UNIQUE (capa_id, sequence), 
	CONSTRAINT fk_capa_actions_capa_id_capas FOREIGN KEY(capa_id) REFERENCES capas (id) ON DELETE CASCADE, 
	CONSTRAINT fk_capa_actions_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_capa_actions_completion_evidence_item_id_evidence_items FOREIGN KEY(completion_evidence_item_id) REFERENCES evidence_items (id) ON DELETE SET NULL
);

CREATE INDEX ix_capa_actions_status_due ON capa_actions (status, due_date);


CREATE TABLE effectiveness_checks (
	id UUID NOT NULL, 
	capa_id UUID NOT NULL, 
	method TEXT NOT NULL, 
	target VARCHAR(500) NOT NULL, 
	due_date DATE, 
	sample_size INTEGER, 
	status VARCHAR(32) NOT NULL, 
	result TEXT, 
	effective BOOLEAN, 
	checked_by UUID, 
	checked_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_effectiveness_checks PRIMARY KEY (id), 
	CONSTRAINT fk_effectiveness_checks_capa_id_capas FOREIGN KEY(capa_id) REFERENCES capas (id) ON DELETE CASCADE, 
	CONSTRAINT fk_effectiveness_checks_checked_by_users FOREIGN KEY(checked_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_effectiveness_capa_status_due ON effectiveness_checks (capa_id, status, due_date);


CREATE TABLE intelligence_action_plans (
	id UUID NOT NULL, 
	site_id UUID NOT NULL, 
	recommendation_id UUID NOT NULL, 
	measurable_element_id UUID, 
	code VARCHAR(64) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	objective TEXT NOT NULL, 
	owner_role_code VARCHAR(64) NOT NULL, 
	verifier_role_code VARCHAR(64) NOT NULL, 
	due_date DATE NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	human_authorized BOOLEAN NOT NULL, 
	submitted_at TIMESTAMP WITH TIME ZONE, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_by UUID, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	outcome_summary TEXT, 
	linked_finding_id UUID, 
	linked_capa_id UUID, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_intelligence_action_plans PRIMARY KEY (id), 
	CONSTRAINT uq_intelligence_action_plans_site_id UNIQUE (site_id, code), 
	CONSTRAINT uq_intelligence_action_plans_recommendation_id UNIQUE (recommendation_id), 
	CONSTRAINT fk_intelligence_action_plans_site_id_sites FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
	CONSTRAINT fk_intelligence_action_plans_recommendation_id_ai_recom_a37f FOREIGN KEY(recommendation_id) REFERENCES ai_recommendations (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_intelligence_action_plans_measurable_element_id_meas_4546 FOREIGN KEY(measurable_element_id) REFERENCES measurable_elements (id) ON DELETE SET NULL, 
	CONSTRAINT fk_intelligence_action_plans_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_intelligence_action_plans_completed_by_users FOREIGN KEY(completed_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_intelligence_action_plans_linked_finding_id_findings FOREIGN KEY(linked_finding_id) REFERENCES findings (id) ON DELETE SET NULL, 
	CONSTRAINT fk_intelligence_action_plans_linked_capa_id_capas FOREIGN KEY(linked_capa_id) REFERENCES capas (id) ON DELETE SET NULL, 
	CONSTRAINT fk_intelligence_action_plans_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_intelligence_action_plan_site_status_due ON intelligence_action_plans (site_id, status, due_date);


CREATE TABLE intelligence_action_reviews (
	id UUID NOT NULL, 
	action_plan_id UUID NOT NULL, 
	review_type VARCHAR(32) NOT NULL, 
	decision VARCHAR(32) NOT NULL, 
	comment TEXT NOT NULL, 
	reviewer_role_code VARCHAR(64) NOT NULL, 
	reviewed_by UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_intelligence_action_reviews PRIMARY KEY (id), 
	CONSTRAINT fk_intelligence_action_reviews_action_plan_id_intellige_5a05 FOREIGN KEY(action_plan_id) REFERENCES intelligence_action_plans (id) ON DELETE CASCADE, 
	CONSTRAINT fk_intelligence_action_reviews_reviewed_by_users FOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_intelligence_action_review_plan_type ON intelligence_action_reviews (action_plan_id, review_type, reviewed_at);


CREATE TABLE intelligence_action_tasks (
	id UUID NOT NULL, 
	action_plan_id UUID NOT NULL, 
	sequence INTEGER NOT NULL, 
	action TEXT NOT NULL, 
	owner_role_code VARCHAR(64) NOT NULL, 
	due_date DATE NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	evidence_reference TEXT, 
	completion_note TEXT, 
	completed_by UUID, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_intelligence_action_tasks PRIMARY KEY (id), 
	CONSTRAINT uq_intelligence_action_tasks_action_plan_id UNIQUE (action_plan_id, sequence), 
	CONSTRAINT fk_intelligence_action_tasks_action_plan_id_intelligenc_9197 FOREIGN KEY(action_plan_id) REFERENCES intelligence_action_plans (id) ON DELETE CASCADE, 
	CONSTRAINT fk_intelligence_action_tasks_completed_by_users FOREIGN KEY(completed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_intelligence_action_task_status_due ON intelligence_action_tasks (status, due_date);


CREATE TABLE intelligence_conversion_requests (
	id UUID NOT NULL, 
	action_plan_id UUID NOT NULL, 
	target_type VARCHAR(16) NOT NULL, 
	severity VARCHAR(8), 
	rationale TEXT NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	requested_by UUID, 
	requested_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	executed_by UUID, 
	executed_at TIMESTAMP WITH TIME ZONE, 
	executed_entity_id VARCHAR(128), 
	execution_note TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	row_version INTEGER NOT NULL, 
	CONSTRAINT pk_intelligence_conversion_requests PRIMARY KEY (id), 
	CONSTRAINT fk_intelligence_conversion_requests_action_plan_id_inte_eb1a FOREIGN KEY(action_plan_id) REFERENCES intelligence_action_plans (id) ON DELETE CASCADE, 
	CONSTRAINT fk_intelligence_conversion_requests_requested_by_users FOREIGN KEY(requested_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_intelligence_conversion_requests_approved_by_users FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_intelligence_conversion_requests_executed_by_users FOREIGN KEY(executed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_intelligence_conversion_plan_status ON intelligence_conversion_requests (action_plan_id, status);
