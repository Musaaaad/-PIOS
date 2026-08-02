# PostgreSQL Runtime Acceptance Checklist

Run on a host with Docker or PostgreSQL 16+:

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed_from_json.py
docker compose exec api python scripts/postgres_runtime_smoke.py
curl -fsS http://localhost:8000/ready
```

Acceptance criteria:

- Alembic reaches `0013_sprint13_institutional_pilot_outcomes` (head).
- 92 tables exist (1,305 columns, 72 indexes, 203 foreign keys, 374 constraints).
- Counts are 41 standards, 266 MEs, 63 nested clauses, 75 documents.
- `/ready` returns `database=reachable`.
- Repeating baseline commit with the same `Idempotency-Key` creates one ImportJob.
- Document lifecycle rejects invalid transitions and requires an approved version before `Effective`.

## Sprint 21 status
This checklist previously stated "`0001_initial`" / "28 tables," which was the Sprint 2-era
baseline and had not been updated as later sprints added migrations `0002`-`0013`; corrected above.
The 92/1,305/72/203/374 figures were independently recomputed offline from SQLAlchemy metadata
this sprint and match `reports/schema_metrics_v1.4.json` exactly, but **only at the code/metadata
level** — this checklist's actual acceptance run (`docker compose up`, `alembic upgrade head`,
`/ready`) still requires a live PostgreSQL 16 instance and has not been executed. See
`docs/SPRINT21_RUNTIME_ENABLEMENT_RUNBOOK.md`.
