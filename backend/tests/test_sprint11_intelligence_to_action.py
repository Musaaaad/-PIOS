from datetime import date, datetime, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import AiRecommendation, Capa, Finding, IntelligenceActionPlan

HEADERS = {"Authorization": "Bearer dev:test:SystemAdmin,AccreditationLead,MedicationSafety,PharmacyDirector,CAPAVerifier,MEOwner,CAPAOwner,EvidenceReviewer"}


def _recommendation(client, code="RISK-ACTION"):
    run = client.post("/api/v1/intelligence/risk-runs", headers=HEADERS, json={"code": code, "period_label": "2026-Q3"})
    assert run.status_code == 201, run.text
    generated = client.post(f"/api/v1/intelligence/risk-runs/{run.json()['id']}/recommendations/generate", headers=HEADERS, json={"limit": 1})
    assert generated.status_code == 200, generated.text
    return generated.json()["recommendations"][0]


def _approve_and_adopt(client, rec, suffix="01"):
    reviewed = client.post(f"/api/v1/intelligence/recommendations/{rec['id']}/review", headers=HEADERS, json={"decision": "ApprovedForPlanning", "comment": "Human reviewer accepts this as planning input only."})
    assert reviewed.status_code == 200, reviewed.text
    session = client.post("/api/v1/intelligence/action-review-sessions", headers=HEADERS, json={"code": f"REV-{suffix}", "title": "Human intelligence review committee", "scheduled_at": datetime.now(timezone.utc).isoformat(), "quorum_required": 2})
    assert session.status_code == 201, session.text
    item = client.post(f"/api/v1/intelligence/action-review-sessions/{session.json()['id']}/items", headers=HEADERS, json={"recommendation_id": rec["id"]})
    assert item.status_code == 200, item.text
    decision = client.post(f"/api/v1/intelligence/action-review-items/{item.json()['item']['id']}/decision", headers=HEADERS, json={"decision": "AdoptForPlanning", "rationale": "Committee adopts the recommendation for a governed human-owned plan."})
    assert decision.status_code == 200, decision.text
    return session.json(), item.json()["item"]


def _plan(client, rec, code="ACT-001"):
    response = client.post("/api/v1/intelligence/action-plans", headers=HEADERS, json={
        "recommendation_id": rec["id"], "code": code, "title": "Governed risk-reduction action plan",
        "objective": "Verify the signal and implement a human-approved operational improvement without automatic compliance decisions.",
        "owner_role_code": "MEOwner", "verifier_role_code": "CAPAVerifier", "due_date": date.today().isoformat(),
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_action_plan_requires_human_review_and_recorded_adoption(client):
    rec = _recommendation(client, "RISK-ACTION-1")
    blocked = client.post("/api/v1/intelligence/action-plans", headers=HEADERS, json={
        "recommendation_id": rec["id"], "code": "ACT-BLOCKED", "title": "Blocked action plan",
        "objective": "This should be blocked before the recommendation is human approved and adopted.",
        "owner_role_code": "MEOwner", "due_date": date.today().isoformat(),
    })
    assert blocked.status_code == 409
    _approve_and_adopt(client, rec, "ACTION-1")
    plan = _plan(client, rec, "ACT-001")
    assert plan["status"] == "Draft" and plan["human_authorized"] is True


def test_plan_lifecycle_requires_tasks_approval_and_independent_completion_review(client):
    rec = _recommendation(client, "RISK-ACTION-2")
    _approve_and_adopt(client, rec, "ACTION-2")
    plan = _plan(client, rec, "ACT-002")
    task = client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/tasks", headers=HEADERS, json={"action": "Collect representative evidence and validate the identified risk signal.", "owner_role_code": "MEOwner", "due_date": date.today().isoformat()})
    assert task.status_code == 201, task.text
    submitted = client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/submit", headers=HEADERS, json={"comment": "Submit for independent approval."})
    assert submitted.status_code == 200 and submitted.json()["plan"]["status"] == "Submitted"
    approval = client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/reviews", headers=HEADERS, json={"review_type": "Approval", "decision": "Approve", "comment": "Independent reviewer approves planning and execution.", "reviewer_role_code": "CAPAVerifier"})
    assert approval.status_code == 201
    started = client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/start", headers=HEADERS, json={"comment": "Human owner starts execution."})
    assert started.status_code == 200 and started.json()["status"] == "InProgress"
    completed_task = client.patch(f"/api/v1/intelligence/action-tasks/{task.json()['id']}", headers=HEADERS, json={"status": "Completed", "completion_note": "Evidence reviewed and task completed by the human owner.", "evidence_reference": "EVID-TEST-001"})
    assert completed_task.status_code == 200
    early = client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/complete", headers=HEADERS, json={"outcome_summary": "The human-owned plan completed its defined operational tasks."})
    assert early.status_code == 409
    verify = client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/reviews", headers=HEADERS, json={"review_type": "CompletionVerification", "decision": "Approve", "comment": "Independent verifier confirms the recorded task evidence.", "reviewer_role_code": "CAPAVerifier"})
    assert verify.status_code == 201
    done = client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/complete", headers=HEADERS, json={"outcome_summary": "The human-owned plan completed its tasks and received independent verification."})
    assert done.status_code == 200 and done.json()["status"] == "Completed"


def test_finding_and_capa_require_separate_explicit_conversion_actions(client):
    rec = _recommendation(client, "RISK-ACTION-3")
    _approve_and_adopt(client, rec, "ACTION-3")
    plan = _plan(client, rec, "ACT-003")
    task = client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/tasks", headers=HEADERS, json={"action": "Verify the signal before any governed conversion to a Finding.", "owner_role_code": "MEOwner", "due_date": date.today().isoformat()}).json()
    client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/submit", headers=HEADERS, json={})
    client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/reviews", headers=HEADERS, json={"review_type": "Approval", "decision": "Approve", "comment": "Approved for a human-controlled investigation.", "reviewer_role_code": "CAPAVerifier"})
    client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/start", headers=HEADERS, json={})
    with SessionLocal() as db:
        assert db.scalar(select(Finding)) is None
    request = client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/conversion-requests", headers=HEADERS, json={"target_type": "Finding", "severity": "P1", "rationale": "Human review confirmed a potential gap requiring formal investigation."})
    assert request.status_code == 201 and request.json()["status"] == "Requested"
    decision = client.post(f"/api/v1/intelligence/conversion-requests/{request.json()['id']}/decision", headers=HEADERS, json={"approved": True, "comment": "Authorized human approves creation of a formal Finding."})
    assert decision.status_code == 200
    finding = client.post(f"/api/v1/intelligence/conversion-requests/{request.json()['id']}/execute-finding", headers=HEADERS, json={"criterion": "Governed intelligence review", "problem_statement": "Human reviewers confirmed a gap that requires formal investigation and corrective action governance.", "owner_role_code": "MedicationSafety", "due_date": date.today().isoformat()})
    assert finding.status_code == 201 and finding.json()["source_type"] == "IntelligenceReview"
    capa_request = client.post(f"/api/v1/intelligence/action-plans/{plan['id']}/conversion-requests", headers=HEADERS, json={"target_type": "CAPA", "rationale": "The approved Finding requires a separately governed CAPA draft."})
    assert capa_request.status_code == 201
    client.post(f"/api/v1/intelligence/conversion-requests/{capa_request.json()['id']}/decision", headers=HEADERS, json={"approved": True, "comment": "Authorized human approves creation of a CAPA draft."})
    capa = client.post(f"/api/v1/intelligence/conversion-requests/{capa_request.json()['id']}/execute-capa", headers=HEADERS, json={"title": "Human-governed CAPA draft", "owner_role_code": "CAPAOwner", "verifier_role_code": "CAPAVerifier", "due_date": date.today().isoformat(), "root_cause": "Root cause analysis is documented by a human owner for testing.", "action_plan": "Implement, verify and test effectiveness through the existing CAPA workflow."})
    assert capa.status_code == 201 and capa.json()["status"] == "Draft"
    with SessionLocal() as db:
        assert db.scalar(select(Finding)) is not None
        assert db.scalar(select(Capa)) is not None


def test_review_session_cannot_close_with_pending_decisions(client):
    rec = _recommendation(client, "RISK-ACTION-4")
    client.post(f"/api/v1/intelligence/recommendations/{rec['id']}/review", headers=HEADERS, json={"decision": "ApprovedForPlanning", "comment": "Human reviewer accepts planning input."})
    session = client.post("/api/v1/intelligence/action-review-sessions", headers=HEADERS, json={"code": "REV-PENDING", "title": "Pending decision review", "scheduled_at": datetime.now(timezone.utc).isoformat()}).json()
    client.post(f"/api/v1/intelligence/action-review-sessions/{session['id']}/items", headers=HEADERS, json={"recommendation_id": rec["id"]})
    blocked = client.post(f"/api/v1/intelligence/action-review-sessions/{session['id']}/close", headers=HEADERS, json={"comment": "Attempt close."})
    assert blocked.status_code == 409


def test_action_dashboard_exposes_guardrail(client):
    response = client.get("/api/v1/intelligence/action-dashboard", headers=HEADERS)
    assert response.status_code == 200
    assert "do not create Findings" in response.json()["guardrail"]
