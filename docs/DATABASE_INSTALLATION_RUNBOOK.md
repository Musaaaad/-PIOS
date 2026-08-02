# Database Installation Runbook

This runbook is the operational companion to `docs/DATABASE_MIGRATION_POLICY.md`.
Read that document first if you want to understand *why* this procedure
exists instead of a plain `alembic upgrade head`.

## A. Fresh installation (brand-new PostgreSQL 16 database)

### Prerequisites

- A reachable PostgreSQL 16 server and a database that is genuinely empty
  (no tables in the `public` schema). The script verifies this itself and
  refuses to run against anything else.
- `psql` and Python with this project's backend dependencies installed
  (`pip install -e './backend[dev]'`).
- The following environment variables set (standard libpq names — the
  script never prints or logs their values):

  ```
  PGHOST      PGPORT      PGDATABASE      PGUSER      PGPASSWORD
  ```

### Procedure

```bash
export PGHOST=<host>
export PGPORT=<port>
export PGDATABASE=<empty database name>
export PGUSER=<role with DDL rights on that database>
export PGPASSWORD=<password>       # never echo this
export PIOS_FRESH_INSTALL_REPORT=./fresh_install_report.json   # optional, this is the default

bash backend/scripts/fresh_install_postgresql.sh
```

The script applies the verified schema and seed, verifies catalog metrics
against the documented baseline, runs the full backend test suite against
the new database, and — **only if every one of those steps passed** —
stamps Alembic at head. It stops immediately, with a distinct exit code and
a JSON report explaining exactly why, if:

| Exit code | Meaning |
|---:|---|
| 2 | A required environment variable is missing |
| 10 | The target database is not empty |
| 11 | The root-level and `backend/sql/` copies of the schema or seed file have drifted apart |
| 12 | Schema apply failed (any SQL error — `ON_ERROR_STOP=1` stops on the first one) |
| 13 | Seed apply failed |
| 14 | Catalog metrics did not exactly match 92 tables / 1,305 columns / 72 indexes / 203 foreign keys / 374 constraints |
| 15 | The test suite did not come back exactly 81/81 passed with 0 skipped |
| 16 | `alembic stamp head` itself failed after everything else passed |
| 0 | Success — database is verified and ready to run PIOS against |

Read `$PIOS_FRESH_INSTALL_REPORT` (default `./fresh_install_report.json`)
for the machine-readable result of any run, success or failure.

### After a successful run

The database is at the Alembic head revision (via `stamp`, not `upgrade`),
with the verified schema and baseline seed data loaded, and has just had
the full test suite run against it successfully. It's ready to point the
application at (`PIOS_DATABASE_URL=postgresql+psycopg://...`).

## B. Existing installation upgrade

If you already have a PIOS database that was previously installed via this
same fresh-install script (or any database already stamped at a revision
`0002` or later), standard Alembic commands work normally from that point
forward:

```bash
cd backend
alembic upgrade head
```

**Do not** attempt `alembic upgrade head` against a database that has never
been through the fresh-install script or an equivalent manual `0001`-style
bootstrap — see `docs/DATABASE_MIGRATION_POLICY.md` for why that specific
path is not supported.

## C. What this runbook does not cover

- Object storage (MinIO/S3) provisioning — see `integration_v1.7/README.md`.
- OIDC/Keycloak provisioning — see `deploy/keycloak/pios-realm.json` and
  `docs/OIDC_ENTERPRISE_MAPPING.md`.
- Kubernetes deployment of the resulting database connection — see
  `deploy/k8s/`.

None of those are claimed to work by this runbook; they are separate,
unexecuted concerns tracked in `SPRINT21_RUNTIME_VALIDATION/blocker_register.json`.
