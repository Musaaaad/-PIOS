from datetime import date, datetime, timezone
import hashlib

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.entities import (
    AiRecommendation,
    Capa,
    DecisionQualityReview,
    Finding,
    InstitutionalCommittee,
    IntelligenceReviewItem,
    IntelligenceReviewSession,
    SessionGovernance,
    Site,
)

HEADERS = {"Authorization": "Bearer dev:pilot-user:SystemAdmin,AccreditationLead,PharmacyDirector,MedicationSafety,ReadOnlyAuditor,EvidenceCollector,EvidenceReviewer,MEOwner"}


def _institutional_prerequisites():
    with SessionLocal() as db:
        site = db.scalar(select(Site).where(Site.code == "TGH"))
        committee = InstitutionalCommittee(
            site_id=site.id,
            code="TGH-PILOT-COMMITTEE",
            name_ar="لجنة تجربة مؤسسية",
            name_en="Institutional Pilot Committee",
            purpose="Govern a controlled institutional pilot without converting operational measures into compliance decisions.",
            decision_scope=["IntelligenceRecommendation", "PilotOutcome"],
            status="Active",
            chair_role_code="AccreditationLead",
            secretary_role_code="AccreditationLead",
            quorum_required=3,
            conflict_policy_reference="COI-POLICY-001",
            charter_reference="CHARTER-001",
        )
        db.add(committee); db.flush()
        recommendation = AiRecommendation(
            site_id=site.id,
            recommendation_type="RiskReduction",
            title="Pilot review recommendation",
            recommendation_text="Review a controlled evidence workflow during the institutional pilot.",
            rationale="Synthetic setup for the pilot execution test.",
            confidence=0.8,
            status="HumanApprovedForPlanning",
            source_context={"classification": "Synthetic"},
            prompt_hash="a" * 64,
            model_id="rules-engine-v1",
            guardrail_result={"pass": True},
        )
        db.add(recommendation); db.flush()
        session = IntelligenceReviewSession(
            site_id=site.id,
            code="TGH-PILOT-SESSION-001",
            title="Controlled institutional pilot session",
            scheduled_at=datetime.now(timezone.utc),
            status="Closed",
            chair_role_code="AccreditationLead",
            quorum_required=3,
            opened_at=datetime.now(timezone.utc),
            closed_at=datetime.now(timezone.utc),
        )
        db.add(session); db.flush()
        item = IntelligenceReviewItem(
            session_id=session.id,
            recommendation_id=recommendation.id,
            sequence=1,
            status="DecisionRecorded",
            decision="AdoptForPlanning",
            rationale="Committee reviewed the recommendation, data provenance and human authority boundaries before recording the decision.",
            decided_at=datetime.now(timezone.utc),
        )
        db.add(item); db.flush()
        governance = SessionGovernance(
            review_session_id=session.id,
            committee_id=committee.id,
            status="Ready",
            expected_voting_members=3,
            attended_voting_members=3,
            quorum_met=True,
            conflicts_complete=True,
            unresolved_conflicts=0,
            authorized_roles=["SystemAdmin", "AccreditationLead", "PharmacyDirector"],
            evaluation_json={"ready": True},
            evaluated_at=datetime.now(timezone.utc),
        )
        db.add(governance)
        quality = DecisionQualityReview(
            review_item_id=item.id,
            review_type="PostDecision",
            rationale_score=5,
            evidence_score=4,
            policy_alignment_score=5,
            conflict_management_score=5,
            bias_check_score=4,
            quality_score=92.0,
            outcome="Pass",
            comment="Independent review confirms the decision was documented and remained within human authority.",
            reviewer_role_code="ReadOnlyAuditor",
            reviewed_at=datetime.now(timezone.utc),
        )
        db.add(quality); db.commit()
        return str(committee.id), str(session.id)


def _create_ready_run(client, mode="Synthetic"):
    committee_id, session_id = _institutional_prerequisites()
    payload = {
        "code": f"TGH-INST-PILOT-{mode.upper()}",
        "title": "Turaif controlled institutional pilot",
        "objective": "Validate governed identity, data provenance, committee execution and outcome reporting without making accreditation decisions.",
        "run_mode": mode,
        "period_start": "2026-08-01",
        "period_end": "2026-08-31",
        "committee_id": committee_id,
        "environment_reference": "https://pios-pilot.example.invalid" if mode == "Institutional" else "local-test",
    }
    run = client.post("/api/v1/institutional-pilot/runs", headers=HEADERS, json=payload)
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    issuer = "https://identity.example.invalid" if mode == "Institutional" else "synthetic://identity"
    for i, role in enumerate(["SystemAdmin", "AccreditationLead", "PharmacyDirector"], 1):
        response = client.post(f"/api/v1/institutional-pilot/runs/{run_id}/identities", headers=HEADERS, json={
            "external_subject": f"subject-{mode}-{i}",
            "issuer": issuer,
            "email_hint": f"member{i}@example.invalid",
            "role_codes": [role],
            "site_codes": ["TGH"],
            "authority_verified": True,
            "training_verified": True,
            "site_scope_verified": True,
            "evidence_reference": f"OIDC-EVIDENCE-{i}",
        })
        assert response.status_code == 200, response.text
        assert response.json()["verified"] is True
    source = client.post(f"/api/v1/institutional-pilot/runs/{run_id}/data-sources", headers=HEADERS, json={
        "code": "SOURCE-001",
        "source_system": "PIOS test fixture" if mode == "Synthetic" else "PIOS institutional extract",
        "source_type": "GovernanceRecords",
        "data_classification": mode,
        "period_start": "2026-08-01",
        "period_end": "2026-08-31",
        "record_count": 10,
        "contains_patient_identifiers": False,
        "deidentified_or_tokenized": True,
        "checksum_sha256": "b" * 64,
        "evidence_reference": "DATA-ATTEST-001",
        "attested": True,
    })
    assert source.status_code == 200, source.text
    evaluation = client.post(f"/api/v1/institutional-pilot/runs/{run_id}/evaluate", headers=HEADERS)
    assert evaluation.status_code == 200 and evaluation.json()["evaluation"]["ready"] is True
    active = client.post(f"/api/v1/institutional-pilot/runs/{run_id}/activate", headers=HEADERS)
    assert active.status_code == 200 and active.json()["status"] == "Active"
    link = client.post(f"/api/v1/institutional-pilot/runs/{run_id}/sessions", headers=HEADERS, json={
        "review_session_id": session_id,
        "sequence": 1,
        "live_data_attested": mode == "Institutional",
        "evidence_reference": "SESSION-MINUTES-001",
    })
    assert link.status_code == 201, link.text
    return run_id, link.json()["id"]


def test_identity_subject_is_hashed_and_not_returned(client):
    run_id, _ = _create_ready_run(client, "Synthetic")
    detail = client.get(f"/api/v1/institutional-pilot/runs/{run_id}", headers=HEADERS)
    assert detail.status_code == 200
    identities = detail.json()["identities"]
    assert identities[0]["subject_hash"] == hashlib.sha256(b"subject-Synthetic-1").hexdigest()
    assert "external_subject" not in identities[0]


def test_institutional_mode_rejects_insecure_issuer_and_patient_identifiers(client):
    committee_id, _ = _institutional_prerequisites()
    run = client.post("/api/v1/institutional-pilot/runs", headers=HEADERS, json={
        "code": "TGH-INST-PILOT-SEC", "title": "Institutional security gate",
        "objective": "Verify institutional issuer and privacy gates before any controlled activation is permitted.",
        "run_mode": "Institutional", "period_start": "2026-08-01", "period_end": "2026-08-31",
        "committee_id": committee_id, "environment_reference": "https://pilot.example.invalid",
    }).json()
    insecure = client.post(f"/api/v1/institutional-pilot/runs/{run['id']}/identities", headers=HEADERS, json={
        "external_subject": "real-user", "issuer": "http://identity.invalid", "role_codes": ["SystemAdmin"], "site_codes": ["TGH"],
        "authority_verified": True, "training_verified": True, "site_scope_verified": True, "evidence_reference": "OIDC-1",
    })
    assert insecure.status_code == 422
    phi = client.post(f"/api/v1/institutional-pilot/runs/{run['id']}/data-sources", headers=HEADERS, json={
        "code": "PHI-SOURCE", "source_system": "Source", "source_type": "Records", "data_classification": "Institutional",
        "record_count": 1, "contains_patient_identifiers": True, "deidentified_or_tokenized": False, "evidence_reference": "PHI-REF",
    })
    assert phi.status_code == 422


def test_pilot_completion_requires_quality_and_measured_outcome(client):
    run_id, execution_id = _create_ready_run(client, "Synthetic")
    refreshed = client.post(f"/api/v1/institutional-pilot/session-executions/{execution_id}/refresh", headers=HEADERS)
    assert refreshed.status_code == 200
    assert refreshed.json()["decision_count"] == 1
    assert refreshed.json()["quality_review_count"] == 1
    before_metric = client.get(f"/api/v1/institutional-pilot/runs/{run_id}/completion-evaluation", headers=HEADERS)
    assert before_metric.json()["ready"] is False
    metric = client.post(f"/api/v1/institutional-pilot/runs/{run_id}/metrics", headers=HEADERS, json={
        "code": "DECISION-TIME", "name": "Median decision time", "category": "Governance",
        "direction": "LowerIsBetter", "baseline_value": 72, "current_value": 18, "target_value": 24,
        "unit": "hours", "source_reference": "METRIC-EVIDENCE-001",
    })
    assert metric.status_code == 200 and metric.json()["status"] == "TargetMet"
    client.post(f"/api/v1/institutional-pilot/runs/{run_id}/observation", headers=HEADERS, json={"comment": "Start the controlled observation window after the governed session."})
    completed = client.post(f"/api/v1/institutional-pilot/runs/{run_id}/complete", headers=HEADERS, json={"comment": "Complete the synthetic pilot after independent quality review and outcome measurement."})
    assert completed.status_code == 200 and completed.json()["status"] == "Completed"


def test_report_requires_human_approval_and_never_creates_findings_or_capas(client):
    run_id, execution_id = _create_ready_run(client, "Synthetic")
    client.post(f"/api/v1/institutional-pilot/session-executions/{execution_id}/refresh", headers=HEADERS)
    client.post(f"/api/v1/institutional-pilot/runs/{run_id}/metrics", headers=HEADERS, json={
        "code": "ADOPTION", "name": "Active pilot adoption", "category": "Adoption",
        "direction": "HigherIsBetter", "baseline_value": 0, "current_value": 10, "target_value": 8,
        "unit": "events", "source_reference": "ADOPTION-EVIDENCE",
    })
    client.post(f"/api/v1/institutional-pilot/runs/{run_id}/adoption-events", headers=HEADERS, json={
        "event_type": "GovernedDecision", "role_code": "AccreditationLead", "actor_reference": "pilot-user-1",
        "event_count": 3, "evidence_reference": "AUDIT-EVENTS-001",
    })
    client.post(f"/api/v1/institutional-pilot/runs/{run_id}/feedback", headers=HEADERS, json={
        "respondent_reference": "participant-1", "role_code": "EvidenceReviewer", "category": "Usability", "rating": 4,
        "comment": "The governed workflow is understandable and preserves explicit human approval boundaries.",
    })
    with SessionLocal() as db:
        before_findings = db.scalar(select(func.count(Finding.id)))
        before_capas = db.scalar(select(func.count(Capa.id)))
    report = client.post(f"/api/v1/institutional-pilot/runs/{run_id}/reports", headers=HEADERS, json={
        "code": "PILOT-REPORT-001",
        "conclusions": "The synthetic pilot demonstrates the controlled workflow and auditability under explicit human governance.",
        "limitations": "The run used synthetic data, local SQLite storage and test identities; it is not an institutional readiness or compliance conclusion.",
    })
    assert report.status_code == 201 and report.json()["status"] == "Draft"
    report_id = report.json()["id"]
    approved = client.post(f"/api/v1/institutional-pilot/reports/{report_id}/approve", headers=HEADERS, json={"comment": "Human reviewer approves publication of the synthetic pilot report with limitations."})
    assert approved.status_code == 200 and approved.json()["status"] == "Approved"
    published = client.post(f"/api/v1/institutional-pilot/reports/{report_id}/publish", headers=HEADERS, json={
        "file_uri": "s3://pios-reports/PILOT-REPORT-001.json", "sha256": "c" * 64,
    })
    assert published.status_code == 200 and published.json()["status"] == "Published"
    assert published.json()["data_classification"] == "Synthetic"
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Finding.id))) == before_findings
        assert db.scalar(select(func.count(Capa.id))) == before_capas


def test_feedback_privacy_and_dashboard_guardrail(client):
    run_id, _ = _create_ready_run(client, "Synthetic")
    rejected = client.post(f"/api/v1/institutional-pilot/runs/{run_id}/feedback", headers=HEADERS, json={
        "respondent_reference": "participant", "category": "Safety", "rating": 3,
        "comment": "Contains patient information", "contains_patient_data": True,
    })
    assert rejected.status_code == 422
    dashboard = client.get("/api/v1/institutional-pilot/dashboard", headers=HEADERS)
    assert dashboard.status_code == 200
    assert "do not approve CBAHI compliance" in dashboard.json()["guardrail"]
