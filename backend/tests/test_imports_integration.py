from app.db.session import SessionLocal
from app.models.entities import ImportJob
from sqlalchemy import select, func


def test_import_commit_is_idempotent(client, baseline_payload):
    headers = {"idempotency-key": "baseline-2026-08-01"}
    first = client.post("/api/v1/imports/baseline/commit", headers=headers, json=baseline_payload)
    second = client.post("/api/v1/imports/baseline/commit", headers=headers, json=baseline_payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["job_id"] == second.json()["job_id"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ImportJob)) == 1

    jobs = client.get("/api/v1/imports/jobs")
    assert jobs.status_code == 200
    assert len(jobs.json()) == 1
