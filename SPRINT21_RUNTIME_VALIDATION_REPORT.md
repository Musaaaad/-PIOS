# Sprint 21 Runtime Validation Report

**Baseline:** Integration Candidate v1.7, current repository state (authoritative, per instruction)
**Scope:** Runtime Validation phase — Docker/PostgreSQL/MinIO/OIDC, using only what is genuinely available in this environment. No privileged system services were installed; no sandbox restrictions were bypassed.
**Rule honored throughout:** nothing is reported as PASS unless it actually ran and actually passed. Nothing BLOCKED was converted to PASS.

---

## PHASE 1 — Runtime capability preflight

| Capability | Status | Evidence |
|---|---|---|
| Docker CLI | **AVAILABLE** | `docker --version` → 29.3.1 |
| Docker daemon | **BLOCKED** | `dockerd` binary present, but no daemon running; starting one requires privileged container capabilities (cgroup/network namespace management) not exposed in this sandbox. Not attempted — starting it would mean bypassing a sandbox restriction. |
| Docker Compose | **AVAILABLE** (plugin only) | `docker compose version` → v5.1.1, but non-functional without a daemon |
| PostgreSQL server | **AVAILABLE** | `postgresql-16` is a pre-installed local system service (not Docker); started successfully (`service postgresql start`), connected via `psql`, real version 16.13 |
| PostgreSQL client | **AVAILABLE** | `psql --version` → 16.13 |
| MinIO / S3-compatible service | **BLOCKED** | Not installed anywhere in the environment; not installed by this validation (would mean adding a new system service) |
| Keycloak / OIDC provider | **BLOCKED** | Not installed; same reasoning as above, plus no authorized institutional issuer exists regardless |
| Network / port capability | **AVAILABLE** | Confirmed local port binding (127.0.0.1:55432); outbound HTTPS available via the environment's proxy |

**Consequence:** Phase 2 (PostgreSQL) was fully executable and was executed for real. Phases 3 (Object Storage) and 4 (OIDC) are genuinely blocked by missing infrastructure that this validation was explicitly told not to install, and are reported as such — not simulated, not skipped silently.

---

## PHASE 2 — PostgreSQL validation

Executed against real PostgreSQL 16.13, using an isolated role (`pios_runtime`) and three dedicated databases so schema+seed verification, the Alembic chain test, and the pytest run couldn't interfere with each other.

### Schema apply — **PASS** (after one real fix)

First attempt against `PIOS_MVP_PostgreSQL_Schema_v1.4.sql`: **6 errors**, all one root cause. `IntelligenceReviewItem` in `app/models/entities.py` declared two `UniqueConstraint`s that both resolved to the identical generated name `uq_intelligence_review_items_session_id` (the project's naming convention keys only off the first column, and both constraints start with `session_id`). Postgres rejected the second, which failed that `CREATE TABLE`, which cascaded via foreign-key references into 2 more tables (`committee_conflict_declarations`, `decision_quality_reviews`) and their indexes.

**Fix applied:** gave both constraints explicit, distinct names; regenerated the exported DDL via the project's own `scripts/export_postgres_ddl.py`; propagated identically to the root-level copy. Re-applied to a fresh database: **0 errors.**

### Seed apply — **PASS** (after one real fix)

First attempt against `PIOS_MVP_PostgreSQL_Seed_v1.4.sql`: **650 errors** (i.e., the entire file). Root cause: `TimestampMixin.row_version` is `NOT NULL` with only a Python-side SQLAlchemy `default=1` — no database-level default. The exported seed SQL never lists `row_version` in any `INSERT`, so the very first statement (`organizations`) violated the `NOT NULL` constraint, aborting the transaction; every subsequent statement then failed with "transaction is aborted."

**Fix applied:** added `server_default=text("1")` to `row_version`, the same pattern already used for `created_at`/`updated_at`. Regenerated exported DDL. Re-applied to a fresh database: **0 errors.**

### Post-import verification — **PASS**, exact match on all 5 metrics

| Metric | Expected | Actual |
|---|---:|---:|
| Tables | 92 | **92** |
| Columns | 1,305 | **1,305** |
| Indexes | 72 | **72** |
| Foreign keys | 203 | **203** |
| Constraints | 374 | **374** |

Getting the last two exact required a third real fix, found only by actually running this against Postgres: `integration_v1.7/sql/verify_post_import.sql`'s own queries counted different things than its documented baseline. `pg_indexes` naively returned 241 (it includes the implicit indexes Postgres creates to back every `PRIMARY KEY`/`UNIQUE` constraint — 92 + 77 — in addition to the 72 explicit ones). `information_schema.table_constraints` naively returned 1,347 (it synthesizes one virtual "CHECK"-type row per `NOT NULL` column per the SQL standard — 973 of them — on top of the 374 real, independently-named constraints in `pg_constraint`). **The schema itself was already correct** — verified by querying `pg_constraint` directly, which returned exactly 374 before any script change. The fix was rewriting the verification queries to match their own documented baseline, not the schema.

Seed row-count spot check: 41 standards, 266 measurable elements, 63 nested clauses, 75 documents — all match the documented baseline exactly.

### Alembic `upgrade head` from an empty database — **FAIL** (not fixed — see Phase 5)

- Attempt 1: failed at revision `0006_sprint6_deployment_acceptance` — `StringDataRightTruncation: value too long for character varying(32)`. Alembic's own bookkeeping table (`alembic_version.version_num`) defaults to `VARCHAR(32)`; 7 of this project's 13 revision-id strings exceed that (up to 42 characters). **Fixed** — `migrations/env.py` now pre-creates `alembic_version` with `VARCHAR(255)` before Alembic's own `checkfirst=True` logic runs. This does not rename any revision id or touch any migration file's content.
- Attempt 2 (with that fix): got further, then failed at revision `0011_sprint11_intelligence_to_action` — `DuplicateTable: relation "intelligence_review_sessions" already exists`. Root cause, directly extending the engineering audit's earlier finding: `0001_initial` creates the *entire current* schema via `Base.metadata.create_all()`. Migrations `0002`–`0010` all use raw `CREATE TABLE IF NOT EXISTS` SQL, which tolerates that. Migrations `0011`–`0013` (22 tables total) instead use Alembic's structured `op.create_table()` API, which has no automatic existence guard — so they collide with what `0001` already silently created.
- **Not fixed.** Resolving this means editing the content of migrations `0011`–`0013` (or `0001`), which this validation was explicitly told not to do without separate approval. See Phase 5.

### Test suite against real PostgreSQL — **PASS**

**81/81 passed, 0 failed, 0 errors, 0 skipped** — run via `Base.metadata.create_all()` (a third, independent code path from both the raw-SQL schema/seed files and the Alembic chain). This is the first time in this project's available history the full suite has run against a real PostgreSQL server rather than SQLite.

---

## PHASE 3 — Object Storage validation

**Status: NOT EXECUTED — BLOCKED.** No MinIO or other S3-compatible service is installed or running. Installing one was out of scope (this validation was told to use what's already available, not stand up new infrastructure). None of the 9 sub-checks (upload/download/HEAD/delete, SHA-256, versioning, cross-site denial, admin override, unsafe-scope rejection, malware-test rejection, no public access) were run. Not simulated, not assumed.

## PHASE 4 — OIDC validation

**Status: NOT EXECUTED — BLOCKED.** No Keycloak or other real OIDC provider is installed or running, and no authorized institutional issuer/tenant exists regardless. None of the 11 sub-checks were run.

---

## PHASE 5 — Migration integrity assessment

| Dimension | Finding |
|---|---|
| **Fresh-install correctness** | **FAIL.** `alembic upgrade head` does not complete against an empty database — confirmed, reproducible, root-caused precisely (above). |
| **Incremental migration auditability** | **Compromised.** Because `0001_initial` creates the current (not historical) schema, the migration files after it cannot be used to audit what actually changed sprint-by-sprint from a schema-history perspective — most of `0002`–`0010`'s `CREATE TABLE IF NOT EXISTS` statements are effectively unreachable no-ops against a real fresh install. |
| **Historical reproducibility** | **Not possible.** There is no way to stand up a database representing the schema as it genuinely existed after any single historical migration (e.g., "just after Sprint 5") — `0001` alone always yields the full current schema. |

**Recommended safe, forward-only remediation** (none of this was implemented — it requires your decision):
1. Do not edit `0001_initial.py` or any existing migration file's content.
2. Add a new forward migration that makes the 22 tables currently created via `op.create_table()` in `0011`–`0013` existence-guarded (e.g., check-then-create, or convert to `IF NOT EXISTS` raw SQL in a *new* migration that supersedes them going forward) — this fixes fresh-install correctness without rewriting history.
3. Keep the `alembic_version` column-width fix (`migrations/env.py`) — it's an independent, permanent defect unrelated to the `0001_initial` design question, and doesn't touch history either.
4. A genuine fix for auditability/historical reproducibility would mean rewriting `0001_initial` to be a true fixed snapshot and re-deriving `0002`+ as real incremental deltas — this is a "squash and rewrite history" operation, which is explicitly out of scope here and would need your explicit, separate approval.

---

## PHASE 6 — Deliverables

| # | Deliverable | Location |
|---|---|---|
| 1 | This report | `SPRINT21_RUNTIME_VALIDATION_REPORT.md` |
| 2 | Machine-readable JSON test report | `SPRINT21_RUNTIME_VALIDATION/report.json` |
| 3 | Runtime logs (secrets removed — verified no credential strings appear in any log) | `SPRINT21_RUNTIME_VALIDATION/logs/` (10 files: before/after for schema apply, seed apply, alembic attempts, pytest-on-Postgres, verify-post-import before/after) |
| 4 | Actual PostgreSQL metric results | `SPRINT21_RUNTIME_VALIDATION/postgres_catalog_metrics.json` |
| 5 | Object Storage validation results | N/A — Phase 3 not executed (BLOCKED); recorded in `blocker_register.json` |
| 6 | OIDC validation results | N/A — Phase 4 not executed (BLOCKED); recorded in `blocker_register.json` |
| 7 | Blocker register | `SPRINT21_RUNTIME_VALIDATION/blocker_register.json` |
| 8 | Updated Sprint 21 handoff addendum | `SPRINT21_RUNTIME_VALIDATION_HANDOFF.docx` (new file — the prior offline-phase handoff, `SPRINT21_RUNTIME_ENABLEMENT_HANDOFF.docx`, is left untouched, per "preserve historical baseline artifacts") |
| 9 | New delivery manifest with SHA-256 values | `SPRINT21_RUNTIME_VALIDATION_MANIFEST.txt` |

---

## Files modified (source/config — all justified above, each independently re-verified against SQLite afterward, 81/81 still passing)

| File | Change | Why |
|---|---|---|
| `backend/app/models/entities.py` | `IntelligenceReviewItem`'s two `UniqueConstraint`s given explicit distinct names; `TimestampMixin.row_version` given `server_default=text("1")` | Both are objectively real, reproduced Postgres failures — not hypothetical |
| `backend/sql/001_initial_schema.sql`, `PIOS_MVP_PostgreSQL_Schema_v1.4.sql` | Regenerated from the fixed models via the project's own existing export script | Keeps the exported DDL in sync with the model source of truth |
| `backend/migrations/env.py` | Pre-creates `alembic_version` with `VARCHAR(255)` before Alembic's own table creation | Fixes a real, permanent Alembic bookkeeping defect without touching any migration's content |
| `integration_v1.7/sql/verify_post_import.sql` | Indexes/constraints queries corrected to match the file's own documented baseline | The original queries counted different things than the number they were compared against; the schema was already correct |

**Not modified, by design:** `migrations/versions/0001_initial.py` through `0013_*.py` (no historical migration content was touched, per explicit instruction).

---

## Status

Working tree not yet committed as of this report — commit follows immediately after, containing exactly the files above plus the new deliverables, nothing else. Stopping here per your instruction, awaiting approval before anything further.
