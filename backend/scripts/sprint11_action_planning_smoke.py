import json, os, sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PIOS_ENV", "test")
os.environ.setdefault("PIOS_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("PIOS_ALLOW_DEV_TOKENS", "true")

from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline

Base.metadata.create_all(engine)
with SessionLocal() as db:
    seed_baseline(db, BaselinePayload.model_validate(json.loads((ROOT / "seeds/PIOS_MVP_Import_Data_v1.json").read_text(encoding="utf-8"))))

c = TestClient(app)
H = {"Authorization": "Bearer dev:test:SystemAdmin,AccreditationLead,MedicationSafety,PharmacyDirector,CAPAVerifier,MEOwner,CAPAOwner,EvidenceReviewer"}
run = c.post("/api/v1/intelligence/risk-runs", headers=H, json={"code": "SPRINT11-RISK", "period_label": "Smoke"}).json()
rec = c.post(f"/api/v1/intelligence/risk-runs/{run['id']}/recommendations/generate", headers=H, json={"limit": 1}).json()["recommendations"][0]
c.post(f"/api/v1/intelligence/recommendations/{rec['id']}/review", headers=H, json={"decision": "ApprovedForPlanning", "comment": "Human smoke reviewer approves planning input only."})
session = c.post("/api/v1/intelligence/action-review-sessions", headers=H, json={"code": "SPRINT11-BOARD", "title": "Sprint 11 human decision board", "scheduled_at": datetime.now(timezone.utc).isoformat()}).json()
c.post(f"/api/v1/intelligence/action-review-sessions/{session['id']}/open", headers=H)
item = c.post(f"/api/v1/intelligence/action-review-sessions/{session['id']}/items", headers=H, json={"recommendation_id": rec["id"]}).json()["item"]
c.post(f"/api/v1/intelligence/action-review-items/{item['id']}/decision", headers=H, json={"decision": "AdoptForPlanning", "rationale": "Human committee adopts the item for planning."})
session = c.post(f"/api/v1/intelligence/action-review-sessions/{session['id']}/close", headers=H, json={"comment": "Smoke session closed after decision."}).json()
plan = c.post("/api/v1/intelligence/action-plans", headers=H, json={"recommendation_id": rec["id"], "code": "SPRINT11-ACTION", "title": "Governed action plan smoke", "objective": "Demonstrate human-controlled intelligence-to-action traceability without automatic compliance decisions.", "owner_role_code": "MEOwner", "verifier_role_code": "CAPAVerifier", "due_date": date.today().isoformat()}).json()
task = c.post(f"/api/v1/intelligence/action-plans/{plan['id']}/tasks", headers=H, json={"action": "Verify the source signal and record representative evidence.", "owner_role_code": "MEOwner", "due_date": date.today().isoformat()}).json()
c.post(f"/api/v1/intelligence/action-plans/{plan['id']}/submit", headers=H, json={"comment": "Submit for review."})
c.post(f"/api/v1/intelligence/action-plans/{plan['id']}/reviews", headers=H, json={"review_type": "Approval", "decision": "Approve", "comment": "Independent approval for test execution.", "reviewer_role_code": "CAPAVerifier"})
c.post(f"/api/v1/intelligence/action-plans/{plan['id']}/start", headers=H, json={"comment": "Start."})
c.patch(f"/api/v1/intelligence/action-tasks/{task['id']}", headers=H, json={"status": "Completed", "completion_note": "Human owner completed the task.", "evidence_reference": "SMOKE-EVID-001"})
conv = c.post(f"/api/v1/intelligence/action-plans/{plan['id']}/conversion-requests", headers=H, json={"target_type": "Finding", "severity": "P1", "rationale": "Human reviewers confirmed a formal investigation is required."}).json()
c.post(f"/api/v1/intelligence/conversion-requests/{conv['id']}/decision", headers=H, json={"approved": True, "comment": "Human authority approves Finding creation."})
finding = c.post(f"/api/v1/intelligence/conversion-requests/{conv['id']}/execute-finding", headers=H, json={"criterion": "Sprint 11 governed smoke", "problem_statement": "Human review confirmed a test gap requiring formal governance and investigation.", "owner_role_code": "MedicationSafety", "due_date": date.today().isoformat()}).json()
c.post(f"/api/v1/intelligence/action-plans/{plan['id']}/reviews", headers=H, json={"review_type": "CompletionVerification", "decision": "Approve", "comment": "Independent verifier confirms the task record.", "reviewer_role_code": "CAPAVerifier"})
completed = c.post(f"/api/v1/intelligence/action-plans/{plan['id']}/complete", headers=H, json={"outcome_summary": "Action plan tasks and verification completed; the linked Finding remains governed separately."}).json()
dashboard = c.get("/api/v1/intelligence/action-dashboard", headers=H).json()
report = {
    "risk_items": run["summary_json"]["total_me"],
    "review_session_status": session["status"],
    "review_decision": "AdoptForPlanning",
    "action_plan_status": completed["status"],
    "action_tasks": 1,
    "explicit_finding_created": finding["source_type"] == "IntelligenceReview",
    "linked_findings": dashboard["linked_findings"],
    "linked_capas": dashboard["linked_capas"],
    "guardrail": dashboard["guardrail"],
    "warning": "Local SQLite and synthetic actors only; not an institutional decision or production execution.",
}
out = ROOT / "reports" / "sprint11_action_planning_smoke.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
