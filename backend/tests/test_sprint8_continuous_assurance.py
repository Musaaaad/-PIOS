from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import AssuranceControl, Finding

HEADERS = {"Authorization": "Bearer dev:test:SystemAdmin,AccreditationLead,MedicationSafety,EvidenceReviewer,MEOwner,PharmacyDirector"}


def test_bootstrap_cycle_failure_finding_and_close(client):
    first = client.post("/api/v1/assurance/programs/bootstrap-p0", headers=HEADERS)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["created"] == 48 and body["total"] == 48
    program_id = body["program"]["id"]

    second = client.post("/api/v1/assurance/programs/bootstrap-p0", headers=HEADERS)
    assert second.status_code == 200 and second.json()["created"] == 0

    due = datetime.now(timezone.utc) + timedelta(days=14)
    cycle = client.post(
        f"/api/v1/assurance/programs/{program_id}/cycles",
        headers=HEADERS,
        json={"code":"2026-Q3-P0","period_label":"2026-Q3","due_at":due.isoformat()},
    )
    assert cycle.status_code == 201, cycle.text
    detail = client.get(f"/api/v1/assurance/cycles/{cycle.json()['id']}", headers=HEADERS).json()
    assert len(detail["tasks"]) == 48

    failed_task = detail["tasks"][0]
    r = client.post(
        f"/api/v1/assurance/tasks/{failed_task['id']}/complete", headers=HEADERS,
        json={"result":"Fail","comment":"Observed recurring control failure in the assurance cycle."},
    )
    assert r.status_code == 200 and r.json()["finding_id"]

    blocked = client.post(f"/api/v1/assurance/cycles/{cycle.json()['id']}/close", headers=HEADERS)
    assert blocked.status_code == 409

    for task in detail["tasks"][1:]:
        ok = client.post(
            f"/api/v1/assurance/tasks/{task['id']}/complete", headers=HEADERS,
            json={"result":"Pass","evidence_reference":f"test:{task['me_id']}"},
        )
        assert ok.status_code == 200, ok.text
    closed = client.post(f"/api/v1/assurance/cycles/{cycle.json()['id']}/close", headers=HEADERS)
    assert closed.status_code == 200
    assert closed.json()["status"] == "ClosedWithFindings"
    assert closed.json()["summary_json"]["task_fail"] == 1
    with SessionLocal() as db:
        assert db.scalar(select(Finding).where(Finding.source_type == "AssuranceTask")) is not None


def test_data_quality_detects_missing_controls_then_overdue_control(client):
    run = client.post("/api/v1/assurance/data-quality/runs", headers=HEADERS, json={"code":"DQ-BEFORE-CONTROLS"})
    assert run.status_code == 201, run.text
    assert run.json()["summary_json"]["by_severity"]["P0"] == 48
    issues = client.get(f"/api/v1/assurance/data-quality/runs/{run.json()['id']}/issues", headers=HEADERS).json()
    assert len(issues) == 48

    boot = client.post("/api/v1/assurance/programs/bootstrap-p0", headers=HEADERS).json()
    with SessionLocal() as db:
        control = db.scalar(select(AssuranceControl).where(AssuranceControl.program_id == UUID(boot["program"]["id"])))
        control.next_due_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    run2 = client.post("/api/v1/assurance/data-quality/runs", headers=HEADERS, json={"code":"DQ-AFTER-CONTROLS"})
    assert run2.status_code == 201, run2.text
    assert run2.json()["summary_json"]["issue_total"] == 1
    assert run2.json()["summary_json"]["by_severity"]["P0"] == 1


def test_cluster_rollout_wave_gate(client):
    wave = client.post("/api/v1/assurance/rollout-waves", headers=HEADERS, json={
        "code":"NBC-WAVE-01", "name":"Northern Border first expansion wave",
        "planned_start":date(2026,9,1).isoformat(), "planned_end":date(2026,12,31).isoformat(),
    })
    assert wave.status_code == 201, wave.text
    site = client.post(f"/api/v1/assurance/rollout-waves/{wave.json()['id']}/sites", headers=HEADERS, json={
        "site_code":"ARH", "name_ar":"مستشفى عرعر التجريبي", "name_en":"Arar Pilot Hospital", "site_type":"Hospital",
    })
    assert site.status_code == 201, site.text
    not_ready = client.patch(f"/api/v1/assurance/rollout-wave-sites/{site.json()['id']}/gates", headers=HEADERS, json={
        "baseline_imported":True,"users_ready":True,"training_complete":False,"deployment_pass":True,"oidc_pass":True,
        "evidence_reference":"ticket:ARH-ONBOARD",
    })
    assert not_ready.status_code == 200 and not_ready.json()["go_live_ready"] is False
    ready = client.patch(f"/api/v1/assurance/rollout-wave-sites/{site.json()['id']}/gates", headers=HEADERS, json={
        "baseline_imported":True,"users_ready":True,"training_complete":True,"deployment_pass":True,"oidc_pass":True,
        "evidence_reference":"ticket:ARH-GO",
    })
    assert ready.status_code == 200 and ready.json()["go_live_ready"] is True
    detail = client.get(f"/api/v1/assurance/rollout-waves/{wave.json()['id']}", headers=HEADERS).json()
    assert detail["wave"]["status"] == "Ready"
    assert detail["wave"]["summary_json"] == {"site_total":1,"site_ready":1,"site_blocked":0}
