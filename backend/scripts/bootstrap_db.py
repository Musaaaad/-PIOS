"""Idempotent database bootstrap for containerised deployments.

This is the deployment-time counterpart to scripts/fresh_install_postgresql.sh.
That script is the supported path for an operator on a machine with `psql`;
this one does the same job from inside an application container, where psql is
not installed but psycopg (a backend dependency) is.

Behaviour, per docs/DATABASE_MIGRATION_POLICY.md:

  * Empty database  -> apply the verified schema, apply the verified seed,
                       verify the five catalog metrics, then `alembic stamp
                       head`. The Alembic migration chain is NOT run, because
                       `alembic upgrade head` cannot complete against an empty
                       database (revision 0011 collides with objects revision
                       0001 already creates).
  * Already set up  -> verify the catalog metrics and exit 0 without writing.
                       Safe to run on every container start / redeploy.

Exits non-zero on any verification failure so a deploy fails loudly rather
than silently serving a half-built database.

Connection string is read from PIOS_DATABASE_URL, falling back to DATABASE_URL
(which is what managed Postgres add-ons such as Render's typically inject).
Either form is normalised to the psycopg driver. Credentials are never logged.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = BACKEND_ROOT / "sql" / "001_initial_schema.sql"
SEED_SQL = BACKEND_ROOT / "sql" / "002_seed_baseline.sql"

EXPECTED = {
    "tables": 92,
    "columns": 1305,
    "indexes": 72,
    "foreign_keys": 203,
    "constraints": 374,
}

# Counted the same way as integration_v1.7/sql/verify_post_import.sql: only
# application-defined objects. pg_indexes also lists the implicit indexes that
# back PRIMARY KEY/UNIQUE constraints, and information_schema.table_constraints
# synthesises a virtual CHECK row per NOT NULL column - neither belongs here.
#
# alembic_version is excluded throughout. It is Alembic's own bookkeeping table,
# not application schema, and it does not exist yet at the point the documented
# 92/1305/72/203/374 baseline was measured. Counting it would make this script
# pass on a first bootstrap (verified before stamping) and then fail on every
# subsequent run (verified after stamping, when the table exists) - i.e. it
# would break every redeploy.
_NOT_ALEMBIC_INFOSCHEMA = "AND table_name <> 'alembic_version'"
# IS DISTINCT FROM, not <>: to_regclass() returns NULL before the table exists
# (i.e. on a first bootstrap, verified prior to stamping), and `conrelid <> NULL`
# evaluates to NULL, which would silently filter out every row and report zero.
_NOT_ALEMBIC_PGCLASS = (
    "AND conrelid IS DISTINCT FROM to_regclass('public.alembic_version')"
)
METRIC_SQL = {
    "tables": "SELECT count(*) FROM information_schema.tables "
              f"WHERE table_schema='public' AND table_type='BASE TABLE' {_NOT_ALEMBIC_INFOSCHEMA}",
    "columns": "SELECT count(*) FROM information_schema.columns "
               f"WHERE table_schema='public' {_NOT_ALEMBIC_INFOSCHEMA}",
    "indexes": "SELECT count(*) FROM pg_indexes i WHERE i.schemaname='public' "
               "AND i.tablename <> 'alembic_version' "
               "AND NOT EXISTS (SELECT 1 FROM pg_constraint c "
               "WHERE c.conname = i.indexname AND c.connamespace='public'::regnamespace)",
    "foreign_keys": "SELECT count(*) FROM pg_constraint "
                    f"WHERE connamespace='public'::regnamespace AND contype='f' {_NOT_ALEMBIC_PGCLASS}",
    "constraints": "SELECT count(*) FROM pg_constraint "
                   f"WHERE connamespace='public'::regnamespace {_NOT_ALEMBIC_PGCLASS}",
}


def log(message: str) -> None:
    print(f"[bootstrap_db] {message}", flush=True)


def normalise_dsn(raw: str) -> str:
    """Return a libpq-compatible DSN, stripping any SQLAlchemy driver suffix."""
    parts = urlsplit(raw)
    scheme = parts.scheme.split("+", 1)[0]
    if scheme == "postgres":
        scheme = "postgresql"
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def redact(dsn: str) -> str:
    parts = urlsplit(dsn)
    host = parts.hostname or "?"
    db = (parts.path or "/?").lstrip("/") or "?"
    return f"{parts.scheme}://<credentials-hidden>@{host}/{db}"


def read_metrics(conn: psycopg.Connection) -> dict[str, int]:
    metrics: dict[str, int] = {}
    with conn.cursor() as cur:
        for name, sql in METRIC_SQL.items():
            cur.execute(sql)
            row = cur.fetchone()
            metrics[name] = int(row[0]) if row else -1
    return metrics


def verify(metrics: dict[str, int]) -> bool:
    ok = metrics == EXPECTED
    rendered = " ".join(f"{k}={metrics.get(k)}" for k in EXPECTED)
    if ok:
        log(f"catalog metrics match the documented baseline: {rendered}")
    else:
        log(f"CATALOG METRIC MISMATCH: got {rendered}")
        log(f"                        expected " + " ".join(f"{k}={v}" for k, v in EXPECTED.items()))
    return ok


def apply_sql_file(conn: psycopg.Connection, path: Path, label: str) -> None:
    if not path.is_file():
        raise SystemExit(f"[bootstrap_db] required {label} file is missing from the image: {path}")
    log(f"applying {label} ({path.name}, {path.stat().st_size} bytes)")
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)  # multi-statement; the seed file manages its own transaction
    log(f"{label} applied")


def main() -> int:
    raw = os.environ.get("PIOS_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not raw:
        log("neither PIOS_DATABASE_URL nor DATABASE_URL is set")
        return 2
    dsn = normalise_dsn(raw)
    log(f"target: {redact(dsn)}")

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
            )
            row = cur.fetchone()
            existing = int(row[0]) if row else 0

        if existing:
            log(f"database already initialised ({existing} tables present); verifying only")
            return 0 if verify(read_metrics(conn)) else 1

        log("database is empty; performing first-time bootstrap")
        apply_sql_file(conn, SCHEMA_SQL, "schema")
        apply_sql_file(conn, SEED_SQL, "seed")

        if not verify(read_metrics(conn)):
            log("bootstrap FAILED verification; not stamping alembic")
            return 1

    # Stamp only after the schema and seed verified. Imported here so a missing
    # optional dependency cannot break the verify-only path above.
    os.environ["PIOS_DATABASE_URL"] = raw
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.stamp(cfg, "head")
    log("alembic stamped at head; bootstrap complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
