#!/bin/sh
# Keycloak entrypoint for managed platforms (Render, Railway, Fly).
#
# Bridges two conventions Keycloak does not handle on its own:
#   1. The platform assigns a port via $PORT; Keycloak reads KC_HTTP_PORT.
#   2. The platform injects a libpq-style DATABASE_URL; Keycloak needs a JDBC
#      URL plus separate username and password.
#
# Never echoes the password. Fails loudly rather than starting half-configured.
set -eu

export KC_HTTP_PORT="${PORT:-8080}"

if [ -n "${DATABASE_URL:-}" ] && [ -z "${KC_DB_URL:-}" ]; then
  # postgres://user:pass@host:port/db  ->  jdbc:postgresql://host:port/db (+ creds)
  _stripped=$(printf '%s' "$DATABASE_URL" | sed -e 's|^postgres\(ql\)\?://||')
  _creds=$(printf '%s' "$_stripped" | sed -e 's|@.*$||')
  _hostpath=$(printf '%s' "$_stripped" | sed -e 's|^[^@]*@||')
  KC_DB_USERNAME=$(printf '%s' "$_creds" | sed -e 's|:.*$||')
  KC_DB_PASSWORD=$(printf '%s' "$_creds" | sed -e 's|^[^:]*:||')
  KC_DB_URL="jdbc:postgresql://${_hostpath}"
  export KC_DB_USERNAME KC_DB_PASSWORD KC_DB_URL
  echo "[keycloak-entrypoint] derived JDBC URL from DATABASE_URL (credentials hidden)"
fi

if [ -z "${KC_DB_URL:-}" ]; then
  echo "[keycloak-entrypoint] FATAL: no database configured (set DATABASE_URL or KC_DB_URL)" >&2
  exit 2
fi

if [ -z "${KEYCLOAK_ADMIN:-}" ] || [ -z "${KEYCLOAK_ADMIN_PASSWORD:-}" ]; then
  echo "[keycloak-entrypoint] FATAL: KEYCLOAK_ADMIN and KEYCLOAK_ADMIN_PASSWORD are required" >&2
  exit 2
fi

echo "[keycloak-entrypoint] starting Keycloak on port ${KC_HTTP_PORT}"
exec /opt/keycloak/bin/kc.sh start --optimized --import-realm
