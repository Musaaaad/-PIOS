from pathlib import Path
from app.core.config import get_settings

REVIEW_CODES = [
    "AUTHENTICITY", "CURRENCY", "SCOPE", "REPRESENTATIVENESS",
    "TRACEABILITY", "CONSISTENCY", "EOC_MATCH",
]


def _campaign(client):
    response = client.post("/api/v1/evidence-campaigns", json={
        "name": "Turaif Q3 Evidence Campaign",
        "description": "Sprint 2 integration campaign",
        "period_start": "2026-07-01", "period_end": "2026-09-30",
    })
    assert response.status_code == 201, response.text
    cid = response.json()["id"]
    assert client.post(f"/api/v1/evidence-campaigns/{cid}/lifecycle", json={"to_status": "Open"}).status_code == 200
    return cid


def _request(client, cid, me_id="MM.5.3", tool="ECF-O"):
    response = client.post(f"/api/v1/evidence-campaigns/{cid}/requests", json={"requests": [{
        "me_id": me_id, "tool_code": tool, "eoc": ["O", "I"],
        "instructions": "Collect representative evidence"
    }]})
    assert response.status_code == 201, response.text
    return response.json()[0]["id"]


def _item(client, rid, structured=True):
    assert client.post(f"/api/v1/evidence-requests/{rid}/start").status_code == 200
    payload = {
        "source_type": "Observation", "title": "HAM double check tracer",
        "description": "Representative tracer across pharmacy and wards" if structured else None,
        "structured_data": {"observations": 12, "passes": 10} if structured else {},
        "period_start": "2026-07-01", "period_end": "2026-07-31",
        "sample_size": 12, "scope_sites": ["TGH"], "scope_shifts": ["Day", "Night"]
    }
    response = client.post(f"/api/v1/evidence-requests/{rid}/items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _tests(fail=None):
    return [{"test_code": code, "result": "Fail" if code == fail else "Pass"} for code in REVIEW_CODES]


def test_campaign_request_item_upload_submit_accept(client, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "object_storage_backend", "local")
    monkeypatch.setattr(settings, "object_storage_root", str(tmp_path))
    cid = _campaign(client)
    rid = _request(client, cid, me_id="MM.31.1")
    iid = _item(client, rid, structured=False)
    upload = client.post(f"/api/v1/evidence-items/{iid}/files", files={
        "file": ("dispensing.txt", b"clean evidence content", "text/plain")
    })
    assert upload.status_code == 201, upload.text
    assert upload.json()["scan_status"] == "Clean"
    assert Path(upload.json()["storage_uri"].removeprefix("file://")).exists()
    submitted = client.post(f"/api/v1/evidence-items/{iid}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "Submitted"
    assert client.post(f"/api/v1/evidence-items/{iid}/review/start").status_code == 200
    review = client.post(f"/api/v1/evidence-items/{iid}/reviews", json={
        "verdict": "Accepted", "reason_code": "SUFFICIENT", "tests": _tests()
    })
    assert review.status_code == 201, review.text
    assert review.json()["evidence_status"] == "Accepted"
    assert review.json()["finding_id"] is None


def test_rejected_esr_review_creates_p0_finding(client):
    cid = _campaign(client)
    rid = _request(client, cid, me_id="MM.5.3")
    iid = _item(client, rid, structured=True)
    assert client.post(f"/api/v1/evidence-items/{iid}/submit").status_code == 200
    assert client.post(f"/api/v1/evidence-items/{iid}/review/start").status_code == 200
    review = client.post(f"/api/v1/evidence-items/{iid}/reviews", json={
        "verdict": "Rejected", "reason_code": "SCOPE_GAP",
        "comment": "Night shift missing", "tests": _tests("SCOPE")
    })
    assert review.status_code == 201, review.text
    assert review.json()["finding_id"]
    findings = client.get("/api/v1/findings?severity=P0").json()
    assert len(findings) == 1
    assert findings[0]["me_id"] == "MM.5.3"


def test_accepted_verdict_rejects_failed_test(client):
    cid = _campaign(client)
    rid = _request(client, cid, me_id="MM.31.1")
    iid = _item(client, rid)
    client.post(f"/api/v1/evidence-items/{iid}/submit")
    client.post(f"/api/v1/evidence-items/{iid}/review/start")
    response = client.post(f"/api/v1/evidence-items/{iid}/reviews", json={
        "verdict": "Accepted", "reason_code": "INVALID", "tests": _tests("CURRENCY")
    })
    assert response.status_code == 409


def test_submission_requires_file_or_structured_content(client):
    cid = _campaign(client)
    rid = _request(client, cid, me_id="MM.31.1")
    iid = _item(client, rid, structured=False)
    response = client.post(f"/api/v1/evidence-items/{iid}/submit")
    assert response.status_code == 409


def test_file_controls_mime_duplicate_and_eicar(client, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "object_storage_backend", "local")
    monkeypatch.setattr(settings, "object_storage_root", str(tmp_path))
    cid = _campaign(client)
    rid = _request(client, cid, me_id="MM.31.1")
    iid = _item(client, rid)
    bad_type = client.post(f"/api/v1/evidence-items/{iid}/files", files={
        "file": ("run.exe", b"MZ", "application/octet-stream")
    })
    assert bad_type.status_code == 415
    eicar = client.post(f"/api/v1/evidence-items/{iid}/files", files={
        "file": ("scan.txt", b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE", "text/plain")
    })
    assert eicar.status_code == 422
    first = client.post(f"/api/v1/evidence-items/{iid}/files", files={
        "file": ("a.txt", b"same", "text/plain")
    })
    assert first.status_code == 201
    duplicate = client.post(f"/api/v1/evidence-items/{iid}/files", files={
        "file": ("b.txt", b"same", "text/plain")
    })
    assert duplicate.status_code == 409


def test_campaign_lifecycle_and_request_uniqueness(client):
    cid = _campaign(client)
    rid1 = _request(client, cid, me_id="MM.31.1", tool="ECF-O")
    rid2 = _request(client, cid, me_id="MM.31.1", tool="ECF-O")
    assert rid1 == rid2
    assert client.post(f"/api/v1/evidence-campaigns/{cid}/lifecycle", json={"to_status": "Closed"}).status_code == 200
    invalid = client.post(f"/api/v1/evidence-campaigns/{cid}/lifecycle", json={"to_status": "Open"})
    assert invalid.status_code == 409


def test_me_workspace_reflects_collection_started(client):
    before = client.get("/api/v1/measurable-elements/MM.31.1/workspace").json()
    assert before["workspace_state"]["evidence_collection_started"] is False
    cid = _campaign(client)
    _request(client, cid, me_id="MM.31.1")
    after = client.get("/api/v1/measurable-elements/MM.31.1/workspace").json()
    assert after["workspace_state"]["evidence_collection_started"] is True


def test_overdue_filter(client):
    cid = _campaign(client)
    response = client.post(f"/api/v1/evidence-campaigns/{cid}/requests", json={"requests": [{
        "me_id": "MM.31.1", "tool_code": "ECF-O", "due_at": "2020-01-01T00:00:00Z"
    }]})
    assert response.status_code == 201
    rows = client.get("/api/v1/evidence-requests?overdue=true").json()
    assert len(rows) == 1
