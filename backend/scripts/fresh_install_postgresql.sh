#!/usr/bin/env bash
# PIOS fresh-install bootstrap for PostgreSQL 16.
#
# `alembic upgrade head` cannot complete against a fresh/empty database:
# revision 0011_sprint11_intelligence_to_action uses op.create_table() with no
# existence guard and collides with the full current schema that
# 0001_initial already creates via Base.metadata.create_all(). See
# docs/DATABASE_MIGRATION_POLICY.md for the full explanation. This script is
# the supported, tested path for standing up a brand-new database. It does
# NOT modify, replace, or claim to fix the historical migration chain -
# migrations 0001-0013 are never touched by this script.
#
# What it does, in order, stopping immediately (non-zero exit) if any step
# fails:
#   1. Verify the target database is empty (no tables in the public schema).
#   2. Verify the root-level and backend/sql/ copies of the schema and seed
#      files are byte-identical (drift detection).
#   3. Apply the schema file with `psql -v ON_ERROR_STOP=1`.
#   4. Apply the seed file with `psql -v ON_ERROR_STOP=1`.
#   5. Run integration_v1.7/sql/verify_post_import.sql and independently
#      confirm the five catalog metrics exactly match the documented
#      baseline (92 tables / 1305 columns / 72 indexes / 203 foreign keys /
#      374 constraints).
#   6. Run the full backend test suite against this database.
#   7. Only if every prior step succeeded: `alembic stamp head`, marking the
#      database as being at the current migration head without ever running
#      the (broken-for-fresh-installs) migration chain.
#
# A machine-readable JSON report is always written, whether the script
# succeeds or stops early.
#
# Required environment variables (standard libpq names; NEVER printed or
# logged by this script):
#   PGHOST      PGPORT      PGDATABASE      PGUSER      PGPASSWORD
#
# Optional:
#   PIOS_FRESH_INSTALL_REPORT   path for the JSON report
#                                (default: ./fresh_install_report.json)
#
# Exit codes:
#   0   success - schema, seed, verification, and tests all passed and
#       alembic was stamped at head
#   2   usage / environment error (e.g. a required PG* variable is unset)
#   10  database is not empty
#   11  schema/seed file drift detected (root copy != backend/sql copy)
#   12  schema apply failed
#   13  seed apply failed
#   14  catalog metrics did not match the documented baseline
#   15  test suite failed
#   16  alembic stamp failed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$BACKEND_DIR/.." && pwd)"

SCHEMA_FILE_ROOT="$REPO_ROOT/PIOS_MVP_PostgreSQL_Schema_v1.4.sql"
SCHEMA_FILE_BACKEND="$BACKEND_DIR/sql/001_initial_schema.sql"
SEED_FILE_ROOT="$REPO_ROOT/PIOS_MVP_PostgreSQL_Seed_v1.4.sql"
SEED_FILE_BACKEND="$BACKEND_DIR/sql/002_seed_baseline.sql"
VERIFY_SQL="$REPO_ROOT/integration_v1.7/sql/verify_post_import.sql"
REPORT_PATH="${PIOS_FRESH_INSTALL_REPORT:-$REPO_ROOT/fresh_install_report.json}"

EXPECTED_TABLES=92
EXPECTED_COLUMNS=1305
EXPECTED_INDEXES=72
EXPECTED_FKS=203
EXPECTED_CONSTRAINTS=374

STAGE="init"
REASON=""

write_report() {
  local status="$1"
  python3 - "$REPORT_PATH" "$status" "$STAGE" "$REASON" \
    "${TABLES:-null}" "${COLUMNS:-null}" "${INDEXES:-null}" "${FKS:-null}" "${CONSTRAINTS:-null}" \
    "${TESTS_TOTAL:-null}" "${TESTS_PASSED:-null}" "${TESTS_FAILED:-null}" \
    "${ALEMBIC_STAMPED:-false}" <<'PYEOF'
import json, sys, datetime
(_, path, status, stage, reason,
 tables, columns, indexes, fks, constraints,
 tests_total, tests_passed, tests_failed, alembic_stamped) = sys.argv

def num(v):
    return None if v == "null" else int(v)

report = {
    "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "status": status,
    "stopped_at_stage": stage if status != "SUCCESS" else None,
    "reason": reason or None,
    "catalog_metrics": {
        "tables": num(tables), "columns": num(columns), "indexes": num(indexes),
        "foreign_keys": num(fks), "constraints": num(constraints),
    },
    "catalog_metrics_expected": {
        "tables": 92, "columns": 1305, "indexes": 72, "foreign_keys": 203, "constraints": 374,
    },
    "test_suite": {
        "total": num(tests_total), "passed": num(tests_passed), "failed": num(tests_failed),
    },
    "alembic_stamped_head": alembic_stamped == "true",
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
print(f"[fresh_install] report written to {path}", file=sys.stderr)
PYEOF
}

fail() {
  local code="$1"; local stage="$2"; local reason="$3"
  STAGE="$stage"; REASON="$reason"
  echo "[fresh_install] STOPPED at stage '$stage': $reason" >&2
  write_report "FAILED"
  exit "$code"
}

echo "[fresh_install] === PIOS PostgreSQL fresh-install bootstrap ===" >&2

# --- environment check ---------------------------------------------------
STAGE="environment_check"
for var in PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD; do
  if [ -z "${!var:-}" ]; then
    fail 2 "environment_check" "required environment variable $var is not set"
  fi
done
echo "[fresh_install] target: PGHOST=$PGHOST PGPORT=$PGPORT PGDATABASE=$PGDATABASE PGUSER=$PGUSER (password not shown)" >&2

# --- emptiness check -------------------------------------------------------
STAGE="emptiness_check"
TABLE_COUNT="$(psql -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null)" \
  || fail 10 "emptiness_check" "could not query target database"
TABLE_COUNT="$(echo "$TABLE_COUNT" | tr -d '[:space:]')"
if [ "$TABLE_COUNT" != "0" ]; then
  fail 10 "emptiness_check" "target database is not empty ($TABLE_COUNT table(s) already present in schema 'public')"
fi
echo "[fresh_install] target database confirmed empty" >&2

# --- drift check: root copy must match backend/sql copy -------------------
STAGE="drift_check"
schema_root_hash="$(sha256sum "$SCHEMA_FILE_ROOT" | awk '{print $1}')"
schema_backend_hash="$(sha256sum "$SCHEMA_FILE_BACKEND" | awk '{print $1}')"
if [ "$schema_root_hash" != "$schema_backend_hash" ]; then
  fail 11 "drift_check" "schema file drift: $SCHEMA_FILE_ROOT != $SCHEMA_FILE_BACKEND"
fi
seed_root_hash="$(sha256sum "$SEED_FILE_ROOT" | awk '{print $1}')"
seed_backend_hash="$(sha256sum "$SEED_FILE_BACKEND" | awk '{print $1}')"
if [ "$seed_root_hash" != "$seed_backend_hash" ]; then
  fail 11 "drift_check" "seed file drift: $SEED_FILE_ROOT != $SEED_FILE_BACKEND"
fi
echo "[fresh_install] schema/seed checksums verified consistent (schema=$schema_root_hash seed=$seed_root_hash)" >&2

# --- schema apply -----------------------------------------------------------
STAGE="schema_apply"
if ! psql -v ON_ERROR_STOP=1 -f "$SCHEMA_FILE_ROOT" > /tmp/pios_fresh_install_schema.log 2>&1; then
  tail -20 /tmp/pios_fresh_install_schema.log >&2
  fail 12 "schema_apply" "schema apply failed (see stderr above); ON_ERROR_STOP triggered a stop on the first SQL error"
fi
echo "[fresh_install] schema applied cleanly" >&2

# --- seed apply -------------------------------------------------------------
STAGE="seed_apply"
if ! psql -v ON_ERROR_STOP=1 -f "$SEED_FILE_ROOT" > /tmp/pios_fresh_install_seed.log 2>&1; then
  tail -20 /tmp/pios_fresh_install_seed.log >&2
  fail 13 "seed_apply" "seed apply failed (see stderr above); ON_ERROR_STOP triggered a stop on the first SQL error"
fi
echo "[fresh_install] seed applied cleanly" >&2

# --- post-import verification -----------------------------------------------
STAGE="verification"
psql -v ON_ERROR_STOP=1 -f "$VERIFY_SQL" > /tmp/pios_fresh_install_verify.log 2>&1 \
  || fail 14 "verification" "verify_post_import.sql itself failed to run"
TABLES="$(psql -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")"
COLUMNS="$(psql -tAc "SELECT count(*) FROM information_schema.columns WHERE table_schema='public'")"
INDEXES="$(psql -tAc "SELECT count(*) FROM pg_indexes i WHERE i.schemaname='public' AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conname = i.indexname AND c.connamespace = 'public'::regnamespace)")"
FKS="$(psql -tAc "SELECT count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace AND contype='f'")"
CONSTRAINTS="$(psql -tAc "SELECT count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace")"
TABLES="$(echo "$TABLES" | tr -d '[:space:]')"; COLUMNS="$(echo "$COLUMNS" | tr -d '[:space:]')"
INDEXES="$(echo "$INDEXES" | tr -d '[:space:]')"; FKS="$(echo "$FKS" | tr -d '[:space:]')"
CONSTRAINTS="$(echo "$CONSTRAINTS" | tr -d '[:space:]')"
echo "[fresh_install] catalog metrics: tables=$TABLES columns=$COLUMNS indexes=$INDEXES foreign_keys=$FKS constraints=$CONSTRAINTS" >&2

if [ "$TABLES" != "$EXPECTED_TABLES" ] || [ "$COLUMNS" != "$EXPECTED_COLUMNS" ] || \
   [ "$INDEXES" != "$EXPECTED_INDEXES" ] || [ "$FKS" != "$EXPECTED_FKS" ] || \
   [ "$CONSTRAINTS" != "$EXPECTED_CONSTRAINTS" ]; then
  fail 14 "verification" "catalog metrics do not match the documented baseline (expected 92/1305/72/203/374, got $TABLES/$COLUMNS/$INDEXES/$FKS/$CONSTRAINTS)"
fi
echo "[fresh_install] catalog metrics match the documented baseline exactly" >&2

# --- test suite ---------------------------------------------------------
# --ignore the fresh-install bootstrap test file itself: that file's live
# tests invoke THIS script as a subprocess to test it from the outside, so
# running it from inside the script's own test-suite step would recurse.
STAGE="test_suite"
EXPECTED_TESTS=81
export PIOS_DATABASE_URL="postgresql+psycopg://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
PYTEST_JUNIT="$(mktemp)"
set +e
(cd "$BACKEND_DIR" && python -m pytest -q --ignore=tests/test_fresh_install_bootstrap.py --junitxml="$PYTEST_JUNIT") > /tmp/pios_fresh_install_pytest.log 2>&1
PYTEST_EXIT=$?
set -e
unset PIOS_DATABASE_URL
TESTS_TOTAL="$(grep -oE 'tests="[0-9]+"' "$PYTEST_JUNIT" | head -1 | grep -oE '[0-9]+' || echo 0)"
TESTS_FAILED_N="$(grep -oE 'failures="[0-9]+"' "$PYTEST_JUNIT" | head -1 | grep -oE '[0-9]+' || echo 0)"
TESTS_ERRORS_N="$(grep -oE 'errors="[0-9]+"' "$PYTEST_JUNIT" | head -1 | grep -oE '[0-9]+' || echo 0)"
TESTS_SKIPPED_N="$(grep -oE 'skipped="[0-9]+"' "$PYTEST_JUNIT" | head -1 | grep -oE '[0-9]+' || echo 0)"
TESTS_FAILED=$((TESTS_FAILED_N + TESTS_ERRORS_N))
TESTS_PASSED=$((TESTS_TOTAL - TESTS_FAILED - TESTS_SKIPPED_N))
rm -f "$PYTEST_JUNIT"
echo "[fresh_install] test suite: $TESTS_PASSED/$TESTS_TOTAL passed ($TESTS_SKIPPED_N skipped)" >&2
if [ "$PYTEST_EXIT" -ne 0 ] || [ "$TESTS_FAILED" -ne 0 ] || [ "$TESTS_SKIPPED_N" -ne 0 ] || [ "$TESTS_TOTAL" -ne "$EXPECTED_TESTS" ]; then
  tail -30 /tmp/pios_fresh_install_pytest.log >&2
  fail 15 "test_suite" "test suite did not exactly match ${EXPECTED_TESTS}/${EXPECTED_TESTS} passed with 0 skipped (got $TESTS_PASSED/$TESTS_TOTAL passed, $TESTS_SKIPPED_N skipped, pytest exit=$PYTEST_EXIT)"
fi

# --- alembic stamp head ---------------------------------------------------
STAGE="alembic_stamp"
export PIOS_DATABASE_URL="postgresql+psycopg://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
if ! (cd "$BACKEND_DIR" && alembic stamp head) > /tmp/pios_fresh_install_alembic_stamp.log 2>&1; then
  tail -20 /tmp/pios_fresh_install_alembic_stamp.log >&2
  unset PIOS_DATABASE_URL
  fail 16 "alembic_stamp" "alembic stamp head failed after all verification passed"
fi
unset PIOS_DATABASE_URL
echo "[fresh_install] alembic stamped at head" >&2

ALEMBIC_STAMPED=true
STAGE="complete"
write_report "SUCCESS"
echo "[fresh_install] === SUCCESS: database is verified and stamped at head ===" >&2
exit 0
