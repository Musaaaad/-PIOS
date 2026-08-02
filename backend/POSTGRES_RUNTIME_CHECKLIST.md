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

- Alembic reaches `0001_initial`.
- 28 tables exist.
- Counts are 41 standards, 266 MEs, 63 nested clauses, 75 documents.
- `/ready` returns `database=reachable`.
- Repeating baseline commit with the same `Idempotency-Key` creates one ImportJob.
- Document lifecycle rejects invalid transitions and requires an approved version before `Effective`.
