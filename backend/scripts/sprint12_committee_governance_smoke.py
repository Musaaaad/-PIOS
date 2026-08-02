from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PIOS_ENV", "test")
os.environ.setdefault("PIOS_DATABASE_URL", "sqlite+pysqlite:///./sprint12_smoke.db")
os.environ.setdefault("PIOS_ALLOW_DEV_TOKENS", "true")

from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline

HEADERS = {"Authorization": "Bearer dev:smoke:SystemAdmin,AccreditationLead,MedicationSafety,PharmacyDirector,CAPAVerifier,ReadOnlyAuditor,MEOwner"}

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
with SessionLocal() as db:
    payload = BaselinePayload.model_validate(json.loads((ROOT / "seeds/PIOS_MVP_Import_Data_v1.json").read_text(encoding="utf-8")))
    seed_baseline(db, payload)

client = TestClient(app)
run = client.post("/api/v1/intelligence/risk-runs", headers=HEADERS, json={"code": "SPRINT12-SMOKE", "period_label": "2026-Q3"}).json()
rec = client.post(f"/api/v1/intelligence/risk-runs/{run['id']}/recommendations/generate", headers=HEADERS, json={"limit": 1}).json()["recommendations"][0]
client.post(f"/api/v1/intelligence/recommendations/{rec['id']}/review", headers=HEADERS, json={"decision": "ApprovedForPlanning", "comment": "Synthetic human review for local governance smoke only."})
session = client.post("/api/v1/intelligence/action-review-sessions", headers=HEADERS, json={"code": "SPRINT12-SESSION", "title": "Synthetic institutional review session", "scheduled_at": datetime.now(timezone.utc).isoformat(), "quorum_required": 3}).json()
item = client.post(f"/api/v1/intelligence/action-review-sessions/{session['id']}/items", headers=HEADERS, json={"recommendation_id": rec["id"]}).json()["item"]
committee = client.post("/api/v1/institutional-governance/committees", headers=HEADERS, json={
    "code": "TGH-IRC-SMOKE", "name_ar": "لجنة اختبار محلية", "name_en": "Local Smoke Review Committee",
    "purpose": "Validate quorum, conflict declarations, authority and decision metrics with synthetic local data only.",
    "decision_scope": ["IntelligenceRecommendation", "ActionPlanning"], "quorum_required": 3,
    "conflict_policy_reference": "SMOKE-COI", "charter_reference": "SMOKE-CHARTER",
}).json()
members=[]
for code,name,role,chair in [("M1","System Administrator","SystemAdmin",True),("M2","Accreditation Lead","AccreditationLead",False),("M3","Medication Safety","MedicationSafety",False)]:
    members.append(client.post(f"/api/v1/institutional-governance/committees/{committee['id']}/members", headers=HEADERS, json={"member_code":code,"display_name":name,"role_code":role,"chair":chair,"authority_verified":True,"training_verified":True,"evidence_reference":f"SYN-{code}"}).json())
client.post(f"/api/v1/institutional-governance/committees/{committee['id']}/activate", headers=HEADERS)
governance = client.post(f"/api/v1/institutional-governance/review-sessions/{session['id']}/bind", headers=HEADERS, json={"committee_id":committee["id"]}).json()
for member in members:
    client.post(f"/api/v1/institutional-governance/session-governance/{governance['id']}/attendance", headers=HEADERS, json={"membership_id":member["id"],"attended":True,"voting_eligible":True,"signed_reference":f"SYN-ATT-{member['member_code']}"})
    client.post(f"/api/v1/institutional-governance/session-governance/{governance['id']}/conflicts", headers=HEADERS, json={"review_item_id":item["id"],"membership_id":member["id"],"has_conflict":False,"disposition":"NoConflict","evidence_reference":f"SYN-COI-{member['member_code']}"})
evaluation = client.post(f"/api/v1/institutional-governance/session-governance/{governance['id']}/evaluate", headers=HEADERS).json()["evaluation"]
client.post(f"/api/v1/intelligence/action-review-sessions/{session['id']}/open", headers=HEADERS)
decision = client.post(f"/api/v1/intelligence/action-review-items/{item['id']}/decision", headers=HEADERS, json={"decision":"AdoptForPlanning","rationale":"Synthetic committee reviews context, limitations, conflicts and human ownership before adopting a planning decision."}).json()
quality = client.post(f"/api/v1/institutional-governance/review-items/{item['id']}/quality-review", headers=HEADERS, json={"rationale_score":5,"evidence_score":4,"policy_alignment_score":5,"conflict_management_score":5,"bias_check_score":4,"comment":"Synthetic independent quality review confirms documented governance controls.","reviewer_role_code":"ReadOnlyAuditor"}).json()
client.post("/api/v1/institutional-governance/sla-policies", headers=HEADERS, json={"code":"TGH-SLA-SMOKE","name":"Synthetic decision SLA"})
metrics = client.post("/api/v1/institutional-governance/metrics-snapshots", headers=HEADERS, json={"code":"SPRINT12-METRICS","period_start":"2020-01-01T00:00:00+00:00","period_end":"2030-01-01T00:00:00+00:00"}).json()
dashboard = client.get("/api/v1/institutional-governance/dashboard", headers=HEADERS).json()

report = {
    "committee_status": "Active",
    "members": len(members),
    "governance_ready": evaluation["ready"],
    "quorum": f"{evaluation['attended_voting_members']}/{evaluation['quorum_required']}",
    "conflict_declarations": evaluation["declarations_recorded"],
    "decision": decision["decision"],
    "quality_score": quality["quality_score"],
    "metrics_decisions": metrics["decision_count"],
    "sla_breaches": metrics["sla_breach_count"],
    "dashboard_active_committees": dashboard["active_committees"],
    "guardrail": dashboard["guardrail"],
    "warning": "Local SQLite, synthetic committee members and synthetic evidence references only; not an institutional Turaif meeting or accreditation decision."
}
out = ROOT / "reports" / "sprint12_committee_governance_smoke.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
