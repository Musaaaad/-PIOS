"""Fresh-install bootstrap validation.

Static checks always run. The live checks (marked) actually exercise
backend/scripts/fresh_install_postgresql.sh against a real PostgreSQL
database and are skipped with a clear reason if one isn't reachable - they
are not silently faked as passing.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
SCRIPT = BACKEND / "scripts" / "fresh_install_postgresql.sh"
VERIFY_SQL = ROOT / "integration_v1.7" / "sql" / "verify_post_import.sql"

# SHA-256 of migrations/versions/*.py as delivered in Integration Candidate
# v1.7 and re-confirmed unchanged after Sprint 21 Runtime Validation. This is
# a regression guard: if any of these ever change, this test fails, proving
# a historical migration file was touched.
EXPECTED_MIGRATION_HASHES = {
    "0001_initial.py": "78815a281697de07dce7005f31ae057a69eaf1bcb79b1510a139202cc1d98974",
    "0002_sprint2_evidence.py": "08897ce16fa13e448dea7200dd66f3b4f4662b3d7e2f709b3edf8bacfd8df754",
    "0003_sprint3_capa_readiness.py": "2b91b92cca119e49f4a82866555a8055d017783a83673eda0b4f4f70465d5ca6",
    "0004_sprint4_portal.py": "f038f1709b31e3eebec916ad29fc60c859e4027cbfeaa059b0b99066408b6d50",
    "0005_sprint5_pilot.py": "9f4d1b9c4fa8dfabb244b48d2eae2a32235a9fd11d4aa5e51c6358c957f9ab47",
    "0006_sprint6_deployment_acceptance.py": "27777bb46ba0b4bd8ce568336aee974e76d36a15db60a25718350dbd58b07a95",
    "0007_sprint7_operations_cutover.py": "b3ba63f796da6951727cf9ab1fd1bbf236585c686ffad21011e356af0b14837b",
    "0008_sprint8_continuous_assurance.py": "6bdf18e24f48a166f00d69205654fe8337d756ff54635687a8173b76eb270958",
    "0009_sprint9_intelligence_ai_governance.py": "9f04734b5c220c24126620211ae4a0ea9ef5afd0b20cb24143f36bace89d4e90",
    "0010_sprint10_production_governance.py": "6d57b6c0dba6e1d6e6abcee054342c1160cf1bd9a7847365f071a373a373b6c9",
    "0011_sprint11_intelligence_to_action.py": "28798e368e7523d2334dfd6117662cabe889a03ec9ffc12640d4e4ad6034a503",
    "0012_sprint12_committee_decision_analytics.py": "cbe069a7499a6996bba9caa547f856e30c89639fa0fb50350a82caa73c9aaffa",
    "0013_sprint13_institutional_pilot_outcomes.py": "a04b393f7ac77946ff0cd8225923c572bb002588532f89d694c2691ecc36d8de",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# Static checks - no database required
# --------------------------------------------------------------------------

def test_fresh_install_script_exists_and_uses_on_error_stop():
    assert SCRIPT.exists(), f"{SCRIPT} does not exist"
    text = SCRIPT.read_text()
    assert "ON_ERROR_STOP=1" in text
    assert os.access(SCRIPT, os.X_OK), f"{SCRIPT} is not executable"


def test_fresh_install_script_checks_emptiness_before_writing():
    text = SCRIPT.read_text()
    assert "emptiness_check" in text
    assert "information_schema.tables" in text
    empty_idx = text.index("emptiness_check")
    schema_apply_idx = text.index("schema_apply")
    assert empty_idx < schema_apply_idx, "emptiness check must happen before schema apply"


def test_schema_and_seed_checksums_are_internally_consistent():
    schema_root = ROOT / "PIOS_MVP_PostgreSQL_Schema_v1.4.sql"
    schema_backend = BACKEND / "sql" / "001_initial_schema.sql"
    seed_root = ROOT / "PIOS_MVP_PostgreSQL_Seed_v1.4.sql"
    seed_backend = BACKEND / "sql" / "002_seed_baseline.sql"
    assert sha256(schema_root) == sha256(schema_backend), "schema file drift between root and backend/sql copies"
    assert sha256(seed_root) == sha256(seed_backend), "seed file drift between root and backend/sql copies"


def test_verify_post_import_uses_corrected_catalog_definitions():
    text = VERIFY_SQL.read_text()
    # Must query the real catalog (pg_constraint), not the SQL-standard
    # information_schema view, which synthesizes a virtual CHECK-type row
    # per NOT NULL column and would never match the documented baseline.
    assert "pg_constraint" in text
    assert re.search(r"FROM\s+pg_constraint\s+WHERE\s+connamespace='public'::regnamespace\s*;", text), \
        "constraints query must select the full pg_constraint count directly"
    # Indexes query must exclude indexes that back a named constraint
    # (implicit PRIMARY KEY / UNIQUE indexes), matching the SQLAlchemy
    # metadata-level definition the documented baseline (72) was computed from.
    assert "NOT EXISTS" in text and "pg_indexes" in text


def test_alembic_stamp_happens_only_after_verification_in_script_order():
    text = SCRIPT.read_text()
    verification_idx = text.index('STAGE="verification"')
    test_suite_idx = text.index('STAGE="test_suite"')
    stamp_idx = text.index('STAGE="alembic_stamp"')
    assert verification_idx < test_suite_idx < stamp_idx, \
        "script must verify catalog metrics, then run tests, then stamp - in that order"
    # The stamp call itself must be textually after the test-suite failure
    # check that can exit the script. (rindex, not index: the phrase also
    # appears once in the file's descriptive header comment.)
    stamp_call_idx = text.rindex("alembic stamp head")
    test_fail_check_idx = text.index('fail 15 "test_suite"')
    assert test_fail_check_idx < stamp_call_idx


def test_historical_migrations_are_unmodified():
    versions_dir = BACKEND / "migrations" / "versions"
    on_disk = {p.name for p in versions_dir.glob("*.py")}
    assert on_disk == set(EXPECTED_MIGRATION_HASHES), (
        f"migration file set changed: disk={sorted(on_disk)} expected={sorted(EXPECTED_MIGRATION_HASHES)}"
    )
    for name, expected_hash in EXPECTED_MIGRATION_HASHES.items():
        actual = sha256(versions_dir / name)
        assert actual == expected_hash, f"{name} was modified (hash mismatch) - historical migrations must not change"


def test_migration_policy_document_exists_and_names_the_known_gap():
    policy = ROOT / "docs" / "DATABASE_MIGRATION_POLICY.md"
    assert policy.exists()
    text = policy.read_text()
    for marker in ["0001_initial", "0011", "fresh install", "historical"]:
        assert marker.lower() in text.lower(), f"migration policy document must mention '{marker}'"


# --------------------------------------------------------------------------
# Live checks - require a reachable, empty-able PostgreSQL server
# --------------------------------------------------------------------------

def _postgres_env_available() -> dict | None:
    required = ["PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PIOS_FRESH_INSTALL_TEST_DATABASE"]
    if not all(os.environ.get(k) for k in required):
        return None
    env = os.environ.copy()
    # Probe against the admin database, not the target test database, which
    # may not exist yet - that's what _reset_database() is for.
    probe_env = env.copy()
    probe_env["PGDATABASE"] = "postgres"
    try:
        subprocess.run(["psql", "-tAc", "SELECT 1"], env=probe_env, check=True, capture_output=True, timeout=10)
    except Exception:
        return None
    env["PGDATABASE"] = env["PIOS_FRESH_INSTALL_TEST_DATABASE"]
    return env


def _reset_database(env: dict) -> None:
    admin_env = env.copy()
    admin_env["PGDATABASE"] = "postgres"
    dbname = env["PGDATABASE"]
    subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-c", f"DROP DATABASE IF EXISTS {dbname}"], env=admin_env, check=True, capture_output=True)
    subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-c", f"CREATE DATABASE {dbname} OWNER {env['PGUSER']}"], env=admin_env, check=True, capture_output=True)


@pytest.fixture
def postgres_env(tmp_path):
    env = _postgres_env_available()
    if env is None:
        pytest.skip(
            "Live fresh-install test requires PGHOST/PGPORT/PGUSER/PGPASSWORD and "
            "PIOS_FRESH_INSTALL_TEST_DATABASE pointing at a reachable PostgreSQL server; "
            "not configured in this environment, so this check did not run (not a fake pass)."
        )
    env["PIOS_FRESH_INSTALL_REPORT"] = str(tmp_path / "fresh_install_report.json")
    return env


def test_fresh_install_succeeds_and_runs_81_of_81_tests(postgres_env):
    """Covers both 'succeeds on a new PostgreSQL 16 database' and 'the
    resulting database runs 81/81 tests successfully' from a single
    end-to-end run (a full run takes ~85s: 650-statement seed + 81 tests via
    TestClient - deliberately not repeated across two separate tests)."""
    _reset_database(postgres_env)
    result = subprocess.run(["bash", str(SCRIPT)], env=postgres_env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, f"fresh install failed:\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}"

    import json
    report = json.loads(Path(postgres_env["PIOS_FRESH_INSTALL_REPORT"]).read_text())
    assert report["status"] == "SUCCESS"
    assert report["catalog_metrics"] == {"tables": 92, "columns": 1305, "indexes": 72, "foreign_keys": 203, "constraints": 374}
    assert report["test_suite"] == {"total": 81, "passed": 81, "failed": 0}
    assert report["alembic_stamped_head"] is True


def test_fresh_install_rejects_a_non_empty_database(postgres_env):
    _reset_database(postgres_env)
    admin_env = postgres_env.copy()
    subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-c", "CREATE TABLE pre_existing (id int)"], env=admin_env, check=True, capture_output=True)

    result = subprocess.run(["bash", str(SCRIPT)], env=postgres_env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 10, f"expected exit 10 (not empty), got {result.returncode}:\n{result.stderr}"

    import json
    report = json.loads(Path(postgres_env["PIOS_FRESH_INSTALL_REPORT"]).read_text())
    assert report["status"] == "FAILED"
    assert report["stopped_at_stage"] == "emptiness_check"
    assert report["alembic_stamped_head"] is False
