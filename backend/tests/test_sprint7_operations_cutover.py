from datetime import date, datetime, timedelta, timezone
from app.services.deployment_acceptance import ACCEPTANCE_CATALOG
from app.services.operations_control import CUTOVER_CATALOG, DEFAULT_SLOS

ALL_HEADERS = {"Authorization": "Bearer dev:test:PharmacyDirector,AccreditationLead,ReadOnlyAuditor,SystemAdmin,MedicationSafety"}


def create_environment(client):
    payload = {
        "code": "ops-int-01", "name": "Operations integration environment",
        "environment_type": "Integration", "api_base_url": "http://api.local",
        "frontend_base_url": "http://frontend.local", "database_kind": "PostgreSQL",
        "object_storage_kind": "Local", "auth_mode": "Dev", "release_version": "1.0.0",
        "tls_enabled": True, "monitoring_enabled": True,
    }
    r = client.post("/api/v1/deployment/environments", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def make_acceptance_pass(client, environment_id):
    run = client.post(
        f"/api/v1/deployment/environments/{environment_id}/acceptance-runs",
        json={"run_code": "OPS-ACCEPT-001", "scope": "PreGoLive"},
    ).json()
    client.post(f"/api/v1/deployment/acceptance-runs/{run['id']}/execute-automated")
    for code, *_ in ACCEPTANCE_CATALOG:
        r = client.patch(
            f"/api/v1/deployment/acceptance-runs/{run['id']}/checks/{code}",
            json={"status": "Pass", "measured_value": "test", "evidence_reference": "test:evidence"},
        )
        assert r.status_code == 200, (code, r.text)
    detail = client.get(f"/api/v1/deployment/acceptance-runs/{run['id']}").json()
    assert detail["run"]["outcome"] == "Pass"
    return run


def test_slo_bootstrap_measurement_and_automatic_incident(client):
    boot = client.post("/api/v1/operations/slos/bootstrap")
    assert boot.status_code == 200 and boot.json()["total"] == len(DEFAULT_SLOS)
    slos = client.get("/api/v1/operations/slos").json()
    availability = next(x for x in slos if x["code"] == "API_AVAILABILITY")
    now = datetime.now(timezone.utc)
    payload = {
        "window_start": (now - timedelta(hours=1)).isoformat(),
        "window_end": now.isoformat(), "measured_value": 98.0,
        "source": "pytest", "evidence_reference": "metric:api-availability",
    }
    r = client.post(f"/api/v1/operations/slos/{availability['id']}/measurements", json=payload)
    assert r.status_code == 201 and r.json()["status"] == "Breach"
    incidents = client.get("/api/v1/operations/incidents?severity=P0").json()
    assert len(incidents) == 1 and incidents[0]["category"] == "SLO"
    command = client.get("/api/v1/operations/command-center").json()
    assert command["operational_ready"] is False
    assert len(command["slo"]) == len(DEFAULT_SLOS)


def test_incident_lifecycle_requires_root_cause_for_closure(client):
    row = client.post("/api/v1/operations/incidents", json={
        "code": "INC-001", "title": "Evidence storage unavailable",
        "description": "Uploads fail in the pilot environment.", "severity": "P1",
        "category": "Storage", "impact_summary": "Evidence collection is blocked.",
    }).json()
    iid = row["id"]
    for status in ["Acknowledged", "Mitigated", "Resolved"]:
        r = client.post(f"/api/v1/operations/incidents/{iid}/transition", json={"to_status": status, "note": f"Moved to {status}"})
        assert r.status_code == 200, r.text
    blocked = client.post(f"/api/v1/operations/incidents/{iid}/transition", json={"to_status": "Closed", "note": "Close incident"})
    assert blocked.status_code == 409
    closed = client.post(f"/api/v1/operations/incidents/{iid}/transition", json={
        "to_status": "Closed", "note": "Validated recovery", "root_cause": "Expired storage credential",
        "resolution_summary": "Rotated credential and completed private read/write test.",
        "evidence_reference": "ticket:INC-001",
    })
    assert closed.status_code == 200 and closed.json()["status"] == "Closed"
    timeline = client.get(f"/api/v1/operations/incidents/{iid}/timeline").json()
    assert len(timeline) == 5


def test_cutover_blocks_on_incident_and_allows_go_after_closure(client):
    env = create_environment(client)
    make_acceptance_pass(client, env["id"])
    now = datetime.now(timezone.utc)
    cutover = client.post("/api/v1/operations/cutovers", json={
        "environment_id": env["id"], "code": "CUT-001", "name": "Turaif controlled cutover",
        "planned_start": now.isoformat(), "planned_end": (now + timedelta(hours=4)).isoformat(),
    }).json()
    detail = client.get(f"/api/v1/operations/cutovers/{cutover['id']}").json()
    assert len(detail["tasks"]) == len(CUTOVER_CATALOG)
    for task in detail["tasks"]:
        r = client.patch(f"/api/v1/operations/cutovers/{cutover['id']}/tasks/{task['code']}", json={"status": "Pass", "evidence_reference": f"test:{task['code']}"})
        assert r.status_code == 200
    inc = client.post("/api/v1/operations/incidents", json={
        "code": "CUT-BLOCK-001", "title": "OIDC login failure during cutover",
        "description": "Pilot users cannot authenticate during validation.", "severity": "P0", "category": "Identity",
    }).json()
    blocked = client.post(f"/api/v1/operations/cutovers/{cutover['id']}/decision", json={"decision": "Go", "rationale": "Attempt Go while incident is open"})
    assert blocked.status_code == 409
    for status, payload in [
        ("Acknowledged", {}), ("Mitigated", {}),
        ("Resolved", {"root_cause": "OIDC client secret expired", "resolution_summary": "Secret rotated and login retested"}),
        ("Closed", {"root_cause": "OIDC client secret expired", "resolution_summary": "Secret rotated and login retested"}),
    ]:
        body = {"to_status": status, "note": f"{status} incident", **payload}
        assert client.post(f"/api/v1/operations/incidents/{inc['id']}/transition", json=body).status_code == 200
    evaluated = client.post(f"/api/v1/operations/cutovers/{cutover['id']}/evaluate").json()
    assert evaluated["go_ready"] is True
    go = client.post(f"/api/v1/operations/cutovers/{cutover['id']}/decision", json={"decision": "Go", "rationale": "All critical tasks passed and no critical incident remains"})
    assert go.status_code == 200 and go.json()["status"] == "Ready"


def test_operational_baseline_can_publish_but_evidence_ready_claim_is_blocked(client):
    snap = client.post("/api/v1/readiness/snapshots/calculate", json={"period_label": "TGH-BASELINE-001"}).json()
    blocked = client.post("/api/v1/operations/baselines", json={"snapshot_id": snap["id"], "code": "READY-CLAIM-001", "classification": "EvidenceReady"})
    assert blocked.status_code == 409
    created = client.post("/api/v1/operations/baselines", json={"snapshot_id": snap["id"], "code": "OPS-BASE-001", "classification": "OperationalBaseline"})
    assert created.status_code == 201
    rid = created.json()["id"]
    approved = client.post(f"/api/v1/operations/baselines/{rid}/approve", headers=ALL_HEADERS)
    assert approved.status_code == 200 and approved.json()["status"] == "Approved"
    published = client.post(f"/api/v1/operations/baselines/{rid}/publish", headers=ALL_HEADERS)
    assert published.status_code == 200 and published.json()["status"] == "Published"
    assert len(published.json()["release_sha256"]) == 64


def test_command_center_returns_cutover_incident_slo_and_baseline_sections(client):
    client.post("/api/v1/operations/slos/bootstrap")
    snap = client.post("/api/v1/readiness/snapshots/calculate", json={"period_label": "COMMAND-CENTER"}).json()
    base = client.post("/api/v1/operations/baselines", json={"snapshot_id": snap["id"], "code": "CMD-BASE", "classification": "OperationalBaseline"}).json()
    result = client.get("/api/v1/operations/command-center").json()
    assert len(result["slo"]) == 6
    assert result["baseline"]["id"] == base["id"]
    assert "open_incidents" in result and "operational_ready" in result
