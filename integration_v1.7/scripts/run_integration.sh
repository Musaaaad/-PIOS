#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo "BLOCKED: Docker is required"; exit 69; }
docker compose --env-file integration.env -f docker-compose.integration.yml up -d --wait
export PGPASSWORD="${POSTGRES_PASSWORD}"
psql -h 127.0.0.1 -p 55432 -U pios -d pios -f sql/verify_post_import.sql
cd ../backend
PIOS_ENV=test PIOS_DATABASE_URL="postgresql+psycopg://pios:${POSTGRES_PASSWORD}@127.0.0.1:55432/pios" pytest -q
