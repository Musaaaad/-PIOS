#!/usr/bin/env sh
# Container entrypoint for managed-platform deployments (Render, Railway, Fly).
#
# Does three things before handing off to the app server:
#   1. Accepts the platform's injected DATABASE_URL if PIOS_DATABASE_URL is unset.
#   2. Normalises the scheme to the psycopg driver. Managed Postgres add-ons
#      inject "postgres://" or "postgresql://"; SQLAlchemy maps a bare
#      "postgresql://" to psycopg2, which this backend does not install (it
#      depends on psycopg 3), so without this the app fails at import time.
#   3. Runs the idempotent database bootstrap, which creates and verifies the
#      schema on first boot and verifies only on every redeploy.
#
# Binds to the platform-provided $PORT. Never echoes the connection string.
set -eu

if [ -z "${PIOS_DATABASE_URL:-}" ] && [ -n "${DATABASE_URL:-}" ]; then
  PIOS_DATABASE_URL="$DATABASE_URL"
fi

if [ -z "${PIOS_DATABASE_URL:-}" ]; then
  echo "[entrypoint] FATAL: neither PIOS_DATABASE_URL nor DATABASE_URL is set" >&2
  exit 2
fi

PIOS_DATABASE_URL=$(printf '%s' "$PIOS_DATABASE_URL" | sed \
  -e 's|^postgres://|postgresql+psycopg://|' \
  -e 's|^postgresql://|postgresql+psycopg://|')
export PIOS_DATABASE_URL
echo "[entrypoint] database driver normalised to postgresql+psycopg"

if [ "${PIOS_SKIP_DB_BOOTSTRAP:-false}" = "true" ]; then
  echo "[entrypoint] PIOS_SKIP_DB_BOOTSTRAP=true, skipping bootstrap"
else
  echo "[entrypoint] running database bootstrap"
  python scripts/bootstrap_db.py
fi

echo "[entrypoint] starting API on port ${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
