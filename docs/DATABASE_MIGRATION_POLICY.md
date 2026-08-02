# Database Migration Policy

This document defines the supported, tested paths for getting a PostgreSQL
database into a state PIOS can run against, and states plainly what is and
is not possible with the current migration history. It does not change, and
does not claim to fix, migrations `0001_initial` through `0013_*` — those
files are preserved unmodified.

## The known gap

`migrations/versions/0001_initial.py` does not declare a fixed set of
Sprint-1 tables. Its `upgrade()` calls `Base.metadata.create_all(bind=bind,
checkfirst=True)` against the **current** SQLAlchemy metadata — i.e.,
whatever `app/models/entities.py` declares today, which today is the full
92-table schema through Sprint 13. Migrations `0002`–`0010` are written as
raw `CREATE TABLE IF NOT EXISTS` SQL specifically because their authors knew
this (see the comment in `0002_sprint2_evidence.py`), so they tolerate `0001`
having already created everything. Migrations `0011`–`0013`, however, use
Alembic's structured `op.create_table()` API for 22 tables, which has no
automatic existence guard — so on a genuinely fresh database, `alembic
upgrade head` fails at revision `0011_sprint11_intelligence_to_action` with
`DuplicateTable`, because `0001` already created `intelligence_review_sessions`
(and the other 21 tables `0011`–`0013` try to create).

This was confirmed directly against PostgreSQL 16 during Sprint 21 Runtime
Validation, not assumed. See `SPRINT21_RUNTIME_VALIDATION_REPORT.md` and
`SPRINT21_RUNTIME_VALIDATION_REPORT_2.md` for the exact reproduction.

## A. Fresh installation (new database, nothing exists yet)

**Use `backend/scripts/fresh_install_postgresql.sh`.** This is the only
supported path for a brand-new PostgreSQL 16 database. It does not use the
Alembic migration chain at all for schema creation. Instead it:

1. Confirms the target database is empty.
2. Confirms the root-level and `backend/sql/` copies of the schema and seed
   files are checksum-identical (drift detection).
3. Applies `PIOS_MVP_PostgreSQL_Schema_v1.4.sql` and
   `PIOS_MVP_PostgreSQL_Seed_v1.4.sql` with `psql -v ON_ERROR_STOP=1`, so any
   SQL error stops the process immediately rather than leaving a
   partially-applied database.
4. Runs `integration_v1.7/sql/verify_post_import.sql` and independently
   confirms the five catalog metrics exactly match 92 tables / 1,305
   columns / 72 indexes / 203 foreign keys / 374 constraints.
5. Runs the full backend test suite against that database.
6. **Only if every prior step passed**, runs `alembic stamp head` — marking
   the database as being at the current migration head in Alembic's own
   bookkeeping table, without ever running the migration chain that cannot
   complete on a fresh database.

If any step fails, the script stops with a distinct non-zero exit code and
writes a machine-readable JSON report explaining exactly what failed. It
never silently continues past a failure.

## B. Existing installation upgrade (a database already at a known revision)

`alembic upgrade head` is supported **only** starting from a database that is
already stamped at a revision from `0002` onward (i.e., one that has already
had `0001_initial`'s effect applied, whether via an old real run of `0001`
or via the fresh-install script's `alembic stamp head`). From any such
starting point, `0002` through `0013` apply the same way they always have in
every previously-tested environment for this project.

**Do not claim, and do not attempt, a full historical replay of the chain
from an empty database via `alembic upgrade head`.** That path is confirmed
broken (see above) and is not being worked around by disguising it as
supported.

## C. Historical migration auditability

The following is a factual statement about what this migration history can
and cannot be used for, not a defect report requiring action:

- **Migrations `0001`–`0013` are preserved unchanged.** No historical
  migration file's content, revision id, or ordering has been modified by
  this policy or by the fresh-install script.
- **Revision `0001_initial` dynamically creates the current metadata**, not
  a frozen Sprint-1 snapshot. Its actual effect changes depending on what
  `app/models/entities.py` contains at the time it runs, not at the time it
  was written.
- **Revision `0011` collides with objects `0001` already created** on a
  fresh install, for the reason explained above.
- **Consequence: the migration history cannot be used to reproduce any
  historical intermediate schema state** (e.g., "the database exactly as it
  existed after Sprint 5"). Running migrations `0001` through any later
  revision on an empty database always yields the current full schema via
  `0001` alone, not an accurate step-by-step reconstruction of what changed
  in each sprint.

A genuine fix for auditability and historical reproducibility (rewriting
`0001_initial` as a true fixed snapshot and re-deriving later revisions as
real incremental deltas) is a deliberate history-rewrite operation. It is
out of scope for this policy and requires explicit, separate approval before
any historical migration file is touched.
