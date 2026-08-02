# Sprint 21 Runtime Validation Report 2 — Dual-Path Database Strategy

**Continuation of:** `SPRINT21_RUNTIME_VALIDATION_REPORT.md` (the initial PostgreSQL/MinIO/OIDC validation pass)
**Correction applied per your instruction:** the "new forward-only migration" remediation suggested in the prior report was wrong — a migration placed after `0013` can never run, because Alembic already fails to reach it at revision `0011` on a fresh database. That suggestion is withdrawn. This report documents the actual fix: a dual-path strategy that leaves migrations `0001`–`0013` completely untouched.
**Rule honored throughout:** nothing BLOCKED was converted to PASS. MinIO and OIDC remain NOT EXECUTED / BLOCKED.

---

## PHASE 1 — Fresh-install bootstrap

Built `backend/scripts/fresh_install_postgresql.sh`. It does not touch the Alembic migration chain for schema creation at all. In order, stopping immediately on any failure:

1. Verifies all required `PG*` environment variables are set (never prints their values).
2. Verifies the target database is empty (`information_schema.tables` count = 0 in schema `public`).
3. Verifies the root-level and `backend/sql/` copies of the schema and seed files are checksum-identical (drift detection).
4. Applies `PIOS_MVP_PostgreSQL_Schema_v1.4.sql` with `psql -v ON_ERROR_STOP=1`.
5. Applies `PIOS_MVP_PostgreSQL_Seed_v1.4.sql` with `psql -v ON_ERROR_STOP=1`.
6. Runs `integration_v1.7/sql/verify_post_import.sql` and independently re-queries the five catalog metrics, comparing exactly against 92/1,305/72/203/374.
7. Runs the full backend test suite against that database (excluding its own bootstrap-test file, to avoid recursion — see Phase 3), requiring exactly 81/81 passed, 0 skipped.
8. **Only if every prior step passed:** `alembic stamp head`.

Distinct exit codes for every stop condition (2, 10–16), and a machine-readable JSON report written on every run, success or failure, to `$PIOS_FRESH_INSTALL_REPORT`.

### A real bug found and fixed while validating the script itself

First end-to-end run of the script reported `SUCCESS` and "alembic stamped at head" — but a follow-up query against the target database showed `alembic_version` **did not exist**. The `stamp` command's own DDL (creating `alembic_version` with the widened `VARCHAR(255)` column, added in the prior validation pass) was left in an uncommitted implicit transaction that got silently rolled back when the SQLAlchemy connection closed, because `stamp` doesn't otherwise write anything else in that same transaction to force a commit.

**Fix:** `backend/migrations/env.py` now calls `connection.commit()` immediately after creating `alembic_version`, before Alembic's own transaction machinery takes over. Verified directly: re-ran `alembic stamp head` against a fresh database before and after this fix — before, `\dt` showed "Did not find any relations"; after, `SELECT * FROM alembic_version` correctly returned `0013_sprint13_institutional_pilot_outcomes`.

### End-to-end run against a real, fresh PostgreSQL 16 database

```
[fresh_install] target database confirmed empty
[fresh_install] schema/seed checksums verified consistent
[fresh_install] schema applied cleanly
[fresh_install] seed applied cleanly
[fresh_install] catalog metrics: tables=92 columns=1305 indexes=72 foreign_keys=203 constraints=374
[fresh_install] catalog metrics match the documented baseline exactly
[fresh_install] test suite: 81/81 passed (0 skipped)
[fresh_install] alembic stamped at head
[fresh_install] === SUCCESS: database is verified and stamped at head ===
```

Exit code 0. `SELECT * FROM alembic_version` on the resulting database correctly returns `0013_sprint13_institutional_pilot_outcomes`.

### Failure path also verified for real

Re-ran the script against the now-populated database from the run above: exit code **10**, `stopped_at_stage: "emptiness_check"`, reason correctly stated as `"target database is not empty (93 table(s) already present..."`. Not simulated — this is the script's actual behavior against a real database it correctly refused to touch.

---

## PHASE 2 — Migration policy

Documented in **`docs/DATABASE_MIGRATION_POLICY.md`** and **`docs/DATABASE_INSTALLATION_RUNBOOK.md`**:

- **A. Fresh installation:** use `fresh_install_postgresql.sh` exclusively. Verify catalog metrics and tests. Stamp Alembic at head. (Implemented and verified above.)
- **B. Existing installation upgrade:** `alembic upgrade head` is supported only from a database already stamped at revision `0002` or later (i.e., already past whatever `0001_initial` would have done). The full historical chain from a truly empty database is explicitly **not** claimed to work, and is not being disguised as working.
- **C. Historical migration auditability:** migrations `0001`–`0013` are preserved unchanged (verified — see Phase 3). Documented explicitly: `0001_initial` dynamically creates current metadata rather than a Sprint-1 snapshot; `0011` collides with what `0001` already created; the migration history cannot be used to reproduce any historical intermediate schema state.

---

## PHASE 3 — Automated validation

New test file: `backend/tests/test_fresh_install_bootstrap.py`. 9 tests (an earlier draft had 10; two live tests were merged into one to avoid two redundant ~85-second end-to-end runs — see below).

| # | What it checks | Type | Result |
|---|---|---|---|
| 1 | Fresh-install script exists and contains `ON_ERROR_STOP=1` | static | **PASS** |
| 2 | Script's emptiness check happens before schema apply (textual ordering) | static | **PASS** |
| 3 | Schema/seed checksums: root copy == `backend/sql/` copy (both schema and seed) | static | **PASS** |
| 4 | `verify_post_import.sql` uses `pg_constraint` directly and excludes constraint-backing indexes (the corrected definitions from the prior validation pass, not the naive ones) | static | **PASS** |
| 5 | `alembic stamp head` appears strictly after verification and test-suite stages in the script | static | **PASS** |
| 6 | All 13 historical migration files match their recorded SHA-256 exactly (proves none was modified) | static | **PASS** |
| 7 | `docs/DATABASE_MIGRATION_POLICY.md` exists and names the known gap | static | **PASS** |
| 8 | Fresh-install script succeeds end-to-end on a new PostgreSQL 16 database, and that database then runs 81/81 tests | **live** | **PASS** (real run, ~85s, real PostgreSQL 16.13) |
| 9 | Fresh-install script rejects a non-empty database with exit code 10 | **live** | **PASS** (real run) |

The two live tests are skipped, not faked, when `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`/`PIOS_FRESH_INSTALL_TEST_DATABASE` aren't set — confirmed: running the full suite without those variables produces `2 skipped` with an explicit reason string, never a silent pass.

**A second real bug was found and fixed while building this test file:** the live tests invoke the fresh-install script as a subprocess, and the script's own internal test-suite step (step 7 above) runs `pytest` against the same `backend/tests/` directory — which now includes this very file. Without an exclusion, this recursed (nested script invocations spawning nested pytest runs spawning nested script invocations), which is what actually caused an apparent hang during development. **Fixed** by adding `--ignore=tests/test_fresh_install_bootstrap.py` to the script's internal pytest invocation, and by tightening the script's pass condition to require exactly 81 total tests with 0 skipped (previously it only checked for 0 failures, which would have silently miscounted skipped tests as "passed").

Full command executed and its real result:
```
$ PGHOST=127.0.0.1 PGPORT=5432 PGUSER=pios_runtime PGPASSWORD=*** \
  PIOS_FRESH_INSTALL_TEST_DATABASE=pios_freshinstall_pytest \
  pytest -v backend/tests/test_fresh_install_bootstrap.py
======================== 9 passed, 1 warning in 89.67s ========================
```

Full backend suite (`pytest -q` from `backend/`, no ignores, offline/no Postgres env) now collects **90 tests** (the original 81 + these 9): 88 passed, 2 skipped (the two live tests, skipped cleanly with a stated reason), 0 failed. With Postgres env vars present, all 90 pass (verified — see previous section).

---

## PHASE 4 — Deliverables

| Deliverable | Location |
|---|---|
| Fresh-install bootstrap script | `backend/scripts/fresh_install_postgresql.sh` |
| Database installation runbook | `docs/DATABASE_INSTALLATION_RUNBOOK.md` |
| Migration policy document | `docs/DATABASE_MIGRATION_POLICY.md` |
| Machine-readable fresh-install test report (real example) | `SPRINT21_RUNTIME_VALIDATION/fresh_install_report_example.json` |
| This report | `SPRINT21_RUNTIME_VALIDATION_REPORT_2.md` |
| Blocker register (updated) | `SPRINT21_RUNTIME_VALIDATION/blocker_register.json` — BLOCK-03 updated to MITIGATED with the resolution described above; BLOCK-01/02/04 (MinIO, OIDC, Docker daemon) unchanged, still BLOCKED |
| Handoff addendum | `SPRINT21_RUNTIME_VALIDATION_HANDOFF_2.docx` |
| Delivery manifest with SHA-256 | `SPRINT21_RUNTIME_VALIDATION_MANIFEST_2.txt` |
| New automated tests | `backend/tests/test_fresh_install_bootstrap.py` |
| Evidence logs (new) | `SPRINT21_RUNTIME_VALIDATION/logs/11_pytest_fresh_install_bootstrap_tests_PASS.txt`, `.../12_junit_fresh_install_bootstrap.xml` |

---

## Files modified

| File | Change | Why |
|---|---|---|
| `backend/scripts/fresh_install_postgresql.sh` | New | The dual-path bootstrap script |
| `backend/tests/test_fresh_install_bootstrap.py` | New | Phase 3 automated validation, 9 tests, all genuinely executed |
| `backend/migrations/env.py` | Added `connection.commit()` after the `alembic_version` pre-create | Real bug: without it, `alembic stamp head` silently persisted nothing |
| `docs/DATABASE_MIGRATION_POLICY.md` | New | Phase 2 A/B/C policy |
| `docs/DATABASE_INSTALLATION_RUNBOOK.md` | New | Operational how-to |
| `SPRINT21_RUNTIME_VALIDATION/blocker_register.json` | BLOCK-03 updated | Reflects the mitigation without claiming the underlying Alembic issue is fixed |

**Not modified:** `migrations/versions/0001_initial.py` through `0013_*.py` — none of the 13 historical migration files were edited. Verified by SHA-256 in the new test suite (item 6 above), not just asserted.

---

## Status

Working tree not yet committed as of this report; commit follows immediately after, containing exactly the files listed above. Stopping after this validation, per your instruction.
