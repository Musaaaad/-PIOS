from datetime import date, timedelta

REVIEW_CODES = ["AUTHENTICITY", "CURRENCY", "SCOPE", "REPRESENTATIVENESS", "TRACEABILITY", "CONSISTENCY", "EOC_MATCH"]


def create_finding(client, me_id="MM.31.1", severity="P1"):
    r = client.post("/api/v1/findings", json={
        "me_id": me_id, "criterion": f"Criterion for {me_id}", "severity": severity,
        "problem_statement": "A verified operational gap requires corrective action.",
        "owner_role_code": "MEOwner", "due_date": str(date.today() + timedelta(days=30)),
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def create_capa(client, finding_id, with_root=True):
    r = client.post(f"/api/v1/findings/{finding_id}/capas", json={
        "title": "Correct the verified medication-management gap",
        "owner_role_code": "CAPAOwner", "verifier_role_code": "CAPAVerifier",
        "due_date": str(date.today() + timedelta(days=30)),
        "root_cause": "The workflow lacks a controlled verification gate." if with_root else None,
        "action_plan": "Implement a controlled workflow, train users, audit execution and verify effectiveness.",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def add_action(client, capa_id, days=10):
    r = client.post(f"/api/v1/capas/{capa_id}/actions", json={
        "action": "Configure the workflow and complete role-based training.",
        "owner_role_code": "CAPAOwner", "due_date": str(date.today() + timedelta(days=days)),
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def approve_and_complete_action(client, capa_id, action_id):
    assert client.post(f"/api/v1/capas/{capa_id}/submit", json={}).status_code == 200
    assert client.post(f"/api/v1/capas/{capa_id}/approve", json={}).status_code == 200
    r = client.patch(f"/api/v1/capa-actions/{action_id}", json={"status": "Completed", "completion_note": "Configuration, training and audit evidence completed."})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/v1/capas/{capa_id}/implementation/complete", json={}).status_code == 200


def create_effective_check(client, capa_id, effective=True):
    r = client.post(f"/api/v1/capas/{capa_id}/effectiveness-checks", json={
        "method": "Repeat a representative tracer across day and night shifts.",
        "target": "100% adherence with no critical deviation",
        "due_date": str(date.today() + timedelta(days=14)), "sample_size": 20,
    })
    assert r.status_code == 201, r.text
    check_id = r.json()["id"]
    r = client.post(f"/api/v1/effectiveness-checks/{check_id}/complete", json={
        "result": "The repeat sample met the defined target." if effective else "The repeat sample failed the target.",
        "effective": effective,
    })
    assert r.status_code == 200, r.text
    return check_id


def accept_evidence(client, me_id="MM.31.1"):
    c = client.post("/api/v1/evidence-campaigns", json={"name":"Readiness Campaign","period_start":"2026-01-01","period_end":"2026-12-31"}).json()
    client.post(f"/api/v1/evidence-campaigns/{c['id']}/lifecycle", json={"to_status":"Open"})
    req = client.post(f"/api/v1/evidence-campaigns/{c['id']}/requests", json={"requests":[{"me_id":me_id,"tool_code":"ECF-D"}]}).json()[0]
    client.post(f"/api/v1/evidence-requests/{req['id']}/start")
    item = client.post(f"/api/v1/evidence-requests/{req['id']}/items", json={"source_type":"Document","title":"Accepted evidence","structured_data":{"validated":True}}).json()
    client.post(f"/api/v1/evidence-items/{item['id']}/submit")
    client.post(f"/api/v1/evidence-items/{item['id']}/review/start")
    tests = [{"test_code":x,"result":"Pass"} for x in REVIEW_CODES]
    r = client.post(f"/api/v1/evidence-items/{item['id']}/reviews", json={"verdict":"Accepted","reason_code":"SUFFICIENT","tests":tests})
    assert r.status_code == 201, r.text


def test_finding_acknowledge_and_workspace(client):
    fid = create_finding(client)
    ack = client.post(f"/api/v1/findings/{fid}/acknowledge", json={"owner_role_code":"MEOwner","comment":"Accepted for action"})
    assert ack.status_code == 200
    assert ack.json()["status"] == "Acknowledged"
    ws = client.get(f"/api/v1/findings/{fid}").json()
    assert ws["me_id"] == "MM.31.1"
    assert ws["capa"] is None


def test_capa_submission_gate_requires_root_cause_and_action(client):
    fid = create_finding(client)
    cid = create_capa(client, fid, with_root=False)
    assert client.post(f"/api/v1/capas/{cid}/submit", json={}).status_code == 409
    client.patch(f"/api/v1/capas/{cid}", json={"root_cause":"A controlled approval gate was not defined or monitored."})
    assert client.post(f"/api/v1/capas/{cid}/submit", json={}).status_code == 409
    add_action(client, cid)
    assert client.post(f"/api/v1/capas/{cid}/submit", json={}).status_code == 200


def test_full_capa_effectiveness_and_closure(client):
    fid = create_finding(client)
    cid = create_capa(client, fid)
    aid = add_action(client, cid)
    approve_and_complete_action(client, cid, aid)
    create_effective_check(client, cid, True)
    closed = client.post(f"/api/v1/capas/{cid}/close", json={"comment":"Independent effectiveness verification passed."})
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "Closed"
    assert client.get(f"/api/v1/findings/{fid}").json()["finding"]["status"] == "Closed"


def test_cannot_close_before_effectiveness(client):
    fid = create_finding(client)
    cid = create_capa(client, fid); aid = add_action(client, cid)
    approve_and_complete_action(client, cid, aid)
    assert client.post(f"/api/v1/capas/{cid}/close", json={}).status_code == 409


def test_failed_effectiveness_reopens_finding_and_capa(client):
    fid = create_finding(client)
    cid = create_capa(client, fid); aid = add_action(client, cid)
    approve_and_complete_action(client, cid, aid)
    create_effective_check(client, cid, False)
    ws = client.get(f"/api/v1/capas/{cid}").json()
    assert ws["capa"]["status"] == "Reopened"
    assert ws["finding"]["status"] == "Reopened"
    assert ws["finding"]["reopened_count"] == 1


def test_esr_manual_finding_is_forced_to_p0(client):
    fid = create_finding(client, me_id="MM.5.3", severity="P2")
    assert client.get(f"/api/v1/findings/{fid}").json()["finding"]["severity"] == "P0"


def test_non_verifier_cannot_approve_or_close(client):
    fid = create_finding(client); cid = create_capa(client, fid); add_action(client, cid)
    client.post(f"/api/v1/capas/{cid}/submit", json={})
    token = {"Authorization":"Bearer dev:owner:CAPAOwner"}
    assert client.post(f"/api/v1/capas/{cid}/approve", json={}, headers=token).status_code == 403


def test_overdue_capa_queue(client):
    fid = create_finding(client)
    r = client.post(f"/api/v1/findings/{fid}/capas", json={
        "title":"Overdue corrective action plan","owner_role_code":"CAPAOwner","verifier_role_code":"CAPAVerifier",
        "due_date":"2020-01-01","root_cause":"The process lacked a defined control owner.",
        "action_plan":"Implement and verify the missing control with representative evidence."
    })
    assert r.status_code == 201
    rows = client.get("/api/v1/capas?overdue=true").json()
    assert len(rows) == 1


def test_readiness_snapshot_counts_and_critical_gate(client):
    base = client.post("/api/v1/readiness/snapshots/calculate", json={"period_label":"Baseline"})
    assert base.status_code == 201
    assert base.json()["total_me"] == 266
    assert base.json()["readiness_score"] == 0
    accept_evidence(client, "MM.31.1")
    fid = create_finding(client, me_id="MM.5.3", severity="P1")
    snap = client.post("/api/v1/readiness/snapshots/calculate", json={"period_label":"After evidence"}).json()
    assert snap["evidence_sufficient_me"] == 1
    assert snap["open_p0"] == 1
    assert snap["critical_open_actions"] is True
    assert snap["overall_status"] == "CriticalOpenActions"
    assert snap["esr_status"]["MM.5"]["status"] == "Red"


def test_not_applicable_excludes_denominator_and_cannot_bypass_finding(client):
    r = client.put("/api/v1/measurable-elements/MM.27.1/applicability", json={"decision":"NotApplicable","rationale":"Parenteral nutrition compounding is not provided within the approved Turaif service scope."})
    assert r.status_code == 200, r.text
    snap = client.post("/api/v1/readiness/snapshots/calculate", json={"period_label":"N/A test"}).json()
    assert snap["not_applicable_me"] == 1
    assert snap["applicable_me"] == 265
    fid = create_finding(client, me_id="MM.28.1", severity="P1")
    blocked = client.put("/api/v1/measurable-elements/MM.28.1/applicability", json={"decision":"NotApplicable","rationale":"Chemotherapy preparation is not provided within the approved Turaif service scope."})
    assert blocked.status_code == 409


def test_snapshot_detail_has_266_items(client):
    snap = client.post("/api/v1/readiness/snapshots/calculate", json={"period_label":"Detail"}).json()
    detail = client.get(f"/api/v1/readiness/snapshots/{snap['id']}").json()
    assert len(detail["items"]) == 266
