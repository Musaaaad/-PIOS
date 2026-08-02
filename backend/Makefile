.PHONY: test integration lint ddl seed migrate run smoke-sqlite smoke-postgres smoke-evidence smoke-capa smoke-sprint6 smoke-sprint7 smoke-sprint8

test:
	pytest -q

integration:
	pytest -q tests/test_registry_integration.py tests/test_documents_integration.py tests/test_imports_integration.py tests/test_evidence_workflow_integration.py tests/test_capa_readiness_integration.py

lint:
	python -m compileall app scripts migrations

ddl:
	python scripts/export_postgres_ddl.py

seed:
	python scripts/seed_from_json.py

migrate:
	alembic upgrade head

run:
	uvicorn app.main:app --reload

smoke-sqlite:
	PIOS_ENV=test PIOS_DATABASE_URL=sqlite+pysqlite:///:memory: python scripts/sqlite_integration_smoke.py

smoke-evidence:
	PIOS_ENV=test PIOS_DATABASE_URL=sqlite+pysqlite:///:memory: python scripts/evidence_workflow_smoke.py

smoke-capa:
	PIOS_ENV=test PIOS_DATABASE_URL=sqlite+pysqlite:///:memory: python scripts/capa_readiness_smoke.py

smoke-postgres:
	python scripts/postgres_runtime_smoke.py


sprint4-smoke:
	python scripts/sprint4_portal_smoke.py

smoke-sprint5:
	python scripts/sprint5_pilot_smoke.py

smoke-sprint6:
	python scripts/sprint6_deployment_acceptance_smoke.py

smoke-sprint7:
	python scripts/sprint7_operations_smoke.py

smoke-sprint8:
	python scripts/sprint8_assurance_smoke.py
