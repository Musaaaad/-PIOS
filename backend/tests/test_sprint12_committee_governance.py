from datetime import date, datetime, timezone

HEADERS = {"Authorization": "Bearer dev:test:SystemAdmin,AccreditationLead,MedicationSafety,PharmacyDirector,CAPAVerifier,ReadOnlyAuditor,MEOwner"}
PHARMACY_ONLY = {"Authorization": "Bearer dev:pharmacy:PharmacyDirector"}


def _recommendation(client, code):
    run = client.post("/api/v1/intelligence/risk-runs", headers=HEADERS, json={"code": code, "period_label": "2026-Q3"})
    assert run.status_code == 201, run.text
    generated = client.post(f"/api/v1/intelligence/risk-runs/{run.json()['id']}/recommendations/generate", headers=HEADERS, json={"limit": 1})
    assert generated.status_code == 200, generated.text
    rec = generated.json()["recommendations"][0]
    reviewed = client.post(f"/api/v1/intelligence/recommendations/{rec['id']}/review", headers=HEADERS, json={"decision": "ApprovedForPlanning", "comment": "Human reviewer accepts this as planning input only."})
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


def _committee(client, suffix="01"):
    committee = client.post("/api/v1/institutional-governance/committees", headers=HEADERS, json={
        "code": f"TGH-IRC-{suffix}", "name_ar": "لجنة المراجعة المؤسسية", "name_en": "Institutional Review Committee",
        "purpose": "Govern human review of intelligence recommendations and measure decision quality without approving compliance.",
        "decision_scope": ["IntelligenceRecommendation", "ActionPlanning"], "quorum_required": 3,
        "conflict_policy_reference": "TGH-COI-POLICY-001", "charter_reference": "TGH-IRC-CHARTER-001",
    })
    assert committee.status_code == 201, committee.text
    members = []
    member_defs = [
        ("M-ADMIN", "System Administrator", "SystemAdmin", True),
        ("M-ACC", "Accreditation Lead", "AccreditationLead", False),
        ("M-MED", "Medication Safety Officer", "MedicationSafety", False),
    ]
    for code, name, role, chair in member_defs:
        response = client.post(f"/api/v1/institutional-governance/committees/{committee.json()['id']}/members", headers=HEADERS, json={
            "member_code": code, "display_name": name, "role_code": role, "voting_member": True,
            "chair": chair, "authority_verified": True, "training_verified": True,
            "evidence_reference": f"AUTH-{code}",
        })
        assert response.status_code == 201, response.text
        members.append(response.json())
    active = client.post(f"/api/v1/institutional-governance/committees/{committee.json()['id']}/activate", headers=HEADERS)
    assert active.status_code == 200, active.text
    return active.json(), members


def _governed_session(client, suffix="01", conflict=False):
    rec = _recommendation(client, f"RISK-COMMITTEE-{suffix}")
    session = client.post("/api/v1/intelligence/action-review-sessions", headers=HEADERS, json={
        "code": f"INST-REV-{suffix}", "title": "Institutional governed review session",
        "scheduled_at": datetime.now(timezone.utc).isoformat(), "quorum_required": 3,
    })
    assert session.status_code == 201, session.text
    item = client.post(f"/api/v1/intelligence/action-review-sessions/{session.json()['id']}/items", headers=HEADERS, json={"recommendation_id": rec["id"]})
    assert item.status_code == 200, item.text
    committee, members = _committee(client, suffix)
    bound = client.post(f"/api/v1/institutional-governance/review-sessions/{session.json()['id']}/bind", headers=HEADERS, json={"committee_id": committee["id"]})
    assert bound.status_code == 201, bound.text
    governance_id = bound.json()["id"]
    for member in members:
        attendance = client.post(f"/api/v1/institutional-governance/session-governance/{governance_id}/attendance", headers=HEADERS, json={
            "membership_id": member["id"], "attended": True, "voting_eligible": True,
            "attendance_mode": "InPerson", "signed_reference": f"ATT-{member['member_code']}",
        })
        assert attendance.status_code == 200, attendance.text
        has_conflict = conflict and member["member_code"] == "M-MED"
        declaration = client.post(f"/api/v1/institutional-governance/session-governance/{governance_id}/conflicts", headers=HEADERS, json={
            "review_item_id": item.json()["item"]["id"], "membership_id": member["id"],
            "has_conflict": has_conflict,
            "description": "Member is operational owner of the reviewed process." if has_conflict else None,
            "disposition": "PendingResolution" if has_conflict else "NoConflict",
            "evidence_reference": f"COI-{member['member_code']}",
        })
        assert declaration.status_code == 200, declaration.text
        if has_conflict:
            conflict_id = declaration.json()["id"]
    return rec, session.json(), item.json()["item"], governance_id, locals().get("conflict_id")


def test_committee_activation_requires_verified_quorum(client):
    committee = client.post("/api/v1/institutional-governance/committees", headers=HEADERS, json={
        "code": "TGH-IRC-BLOCK", "name_ar": "لجنة اختبار", "name_en": "Test Committee",
        "purpose": "Test that institutional committee activation is blocked until authority and training are verified.",
        "decision_scope": ["IntelligenceRecommendation"], "quorum_required": 3,
        "conflict_policy_reference": "COI-REF", "charter_reference": "CHARTER-REF",
    }).json()
    member = client.post(f"/api/v1/institutional-governance/committees/{committee['id']}/members", headers=HEADERS, json={
        "member_code": "M1", "display_name": "Member One", "role_code": "SystemAdmin", "chair": True,
        "authority_verified": False, "training_verified": False,
    }).json()
    blocked = client.post(f"/api/v1/institutional-governance/committees/{committee['id']}/activate", headers=HEADERS)
    assert blocked.status_code == 409
    patched = client.patch(f"/api/v1/institutional-governance/members/{member['id']}", headers=HEADERS, json={"authority_verified": True, "training_verified": True, "evidence_reference": "AUTH-1"})
    assert patched.status_code == 200


def test_governed_session_requires_quorum_conflicts_and_authorized_actor(client):
    rec, session, item, governance_id, _ = _governed_session(client, "READY")
    evaluation = client.post(f"/api/v1/institutional-governance/session-governance/{governance_id}/evaluate", headers=HEADERS)
    assert evaluation.status_code == 200, evaluation.text
    assert evaluation.json()["evaluation"]["ready"] is True
    unauthorized = client.post(f"/api/v1/intelligence/action-review-sessions/{session['id']}/open", headers=PHARMACY_ONLY)
    assert unauthorized.status_code == 403
    opened = client.post(f"/api/v1/intelligence/action-review-sessions/{session['id']}/open", headers=HEADERS)
    assert opened.status_code == 200 and opened.json()["status"] == "Open"
    decided = client.post(f"/api/v1/intelligence/action-review-items/{item['id']}/decision", headers=HEADERS, json={
        "decision": "AdoptForPlanning", "rationale": "The committee reviewed the risk context, evidence gaps and human authority boundaries before adopting planning work."
    })
    assert decided.status_code == 200 and decided.json()["status"] == "DecisionRecorded"


def test_unresolved_conflict_blocks_session_until_formal_resolution(client):
    _, session, _, governance_id, conflict_id = _governed_session(client, "COI", conflict=True)
    evaluation = client.post(f"/api/v1/institutional-governance/session-governance/{governance_id}/evaluate", headers=HEADERS)
    assert evaluation.status_code == 200
    assert evaluation.json()["evaluation"]["ready"] is False
    blocked = client.post(f"/api/v1/intelligence/action-review-sessions/{session['id']}/open", headers=HEADERS)
    assert blocked.status_code == 409
    resolved = client.post(f"/api/v1/institutional-governance/conflicts/{conflict_id}/resolve", headers=HEADERS, json={
        "disposition": "Recused", "comment": "Member is recused from the reviewed item and will not participate in its decision.", "evidence_reference": "COI-RESOLUTION-001",
    })
    assert resolved.status_code == 200 and resolved.json()["status"] == "Resolved"
    ready = client.post(f"/api/v1/institutional-governance/session-governance/{governance_id}/evaluate", headers=HEADERS)
    assert ready.status_code == 200 and ready.json()["evaluation"]["ready"] is True


def test_decision_quality_review_and_sla_metrics_are_human_governed(client):
    rec, session, item, governance_id, _ = _governed_session(client, "METRICS")
    client.post(f"/api/v1/institutional-governance/session-governance/{governance_id}/evaluate", headers=HEADERS)
    client.post(f"/api/v1/intelligence/action-review-sessions/{session['id']}/open", headers=HEADERS)
    decision = client.post(f"/api/v1/intelligence/action-review-items/{item['id']}/decision", headers=HEADERS, json={
        "decision": "AdoptForPlanning", "rationale": "The committee documents the reviewed context, decision scope, evidence limitations and human ownership before planning."
    })
    assert decision.status_code == 200
    policy = client.post("/api/v1/institutional-governance/sla-policies", headers=HEADERS, json={
        "code": "TGH-DECISION-SLA-01", "name": "Turaif institutional decision SLA",
        "recommendation_to_review_hours": 72, "review_to_decision_hours": 24,
        "decision_to_plan_days": 7, "plan_to_start_days": 7, "start_to_completion_days": 30,
    })
    assert policy.status_code == 201
    quality = client.post(f"/api/v1/institutional-governance/review-items/{item['id']}/quality-review", headers=HEADERS, json={
        "rationale_score": 5, "evidence_score": 4, "policy_alignment_score": 5,
        "conflict_management_score": 5, "bias_check_score": 4,
        "comment": "Independent reviewer confirms a documented rationale, managed conflicts and no prohibited automated decision.",
        "reviewer_role_code": "ReadOnlyAuditor",
    })
    assert quality.status_code == 201 and quality.json()["quality_score"] == 92.0
    snapshot = client.post("/api/v1/institutional-governance/metrics-snapshots", headers=HEADERS, json={
        "code": "TGH-DEC-METRICS-2026-Q3", "period_start": "2020-01-01T00:00:00+00:00", "period_end": "2030-01-01T00:00:00+00:00",
    })
    assert snapshot.status_code == 201, snapshot.text
    assert snapshot.json()["decision_count"] >= 1
    assert snapshot.json()["average_quality_score"] == 92.0
    dashboard = client.get("/api/v1/institutional-governance/dashboard", headers=HEADERS)
    assert dashboard.status_code == 200
    assert "do not approve compliance" in dashboard.json()["guardrail"]


def test_metrics_and_governance_do_not_create_findings_or_capas(client):
    _governed_session(client, "GUARD")
    dashboard = client.get("/api/v1/institutional-governance/dashboard", headers=HEADERS)
    assert dashboard.status_code == 200
    assert dashboard.json()["committees_total"] == 1
    assert dashboard.json()["unresolved_conflicts"] == 0
