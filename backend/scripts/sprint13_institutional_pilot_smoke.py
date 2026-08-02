import json, os, importlib.util, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

os.environ.setdefault("PIOS_ENV", "test")
os.environ.setdefault("PIOS_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("PIOS_ALLOW_DEV_TOKENS", "true")

from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.main import app
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline

Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
payload = BaselinePayload.model_validate(json.loads((ROOT / "seeds/PIOS_MVP_Import_Data_v1.json").read_text(encoding="utf-8")))
with SessionLocal() as db:
    seed_baseline(db, payload)

spec = importlib.util.spec_from_file_location("sprint13_test_helpers", ROOT / "tests/test_sprint13_institutional_pilot.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
client = TestClient(app)
run_id, execution_id = mod._create_ready_run(client, "Synthetic")
client.post(f"/api/v1/institutional-pilot/session-executions/{execution_id}/refresh", headers=mod.HEADERS)
metric = client.post(f"/api/v1/institutional-pilot/runs/{run_id}/metrics", headers=mod.HEADERS, json={
    "code":"DECISION-TIME","name":"Median decision time","category":"Governance","direction":"LowerIsBetter",
    "baseline_value":72,"current_value":18,"target_value":24,"unit":"hours","source_reference":"SMOKE-METRIC-001"
}).json()
client.post(f"/api/v1/institutional-pilot/runs/{run_id}/adoption-events", headers=mod.HEADERS, json={
    "event_type":"GovernedDecision","role_code":"AccreditationLead","actor_reference":"smoke-user","event_count":3,"evidence_reference":"SMOKE-AUDIT-001"
})
client.post(f"/api/v1/institutional-pilot/runs/{run_id}/feedback", headers=mod.HEADERS, json={
    "respondent_reference":"smoke-participant","role_code":"EvidenceReviewer","category":"Usability","rating":4,
    "comment":"Synthetic feedback confirms the governed workflow remains understandable."
})
client.post(f"/api/v1/institutional-pilot/runs/{run_id}/observation", headers=mod.HEADERS, json={"comment":"Begin synthetic observation window."})
completion = client.post(f"/api/v1/institutional-pilot/runs/{run_id}/complete", headers=mod.HEADERS, json={"comment":"Complete synthetic pilot after quality and outcome gates."})
report = client.post(f"/api/v1/institutional-pilot/runs/{run_id}/reports", headers=mod.HEADERS, json={
    "code":"SYNTH-PILOT-REPORT-001",
    "conclusions":"The synthetic run demonstrates identity, provenance, governed session and outcome reporting controls.",
    "limitations":"The run uses local SQLite, synthetic identities and synthetic evidence references and is not institutional readiness evidence."
}).json()
client.post(f"/api/v1/institutional-pilot/reports/{report['id']}/approve", headers=mod.HEADERS, json={"comment":"Human approval of synthetic report for technical validation only."})
published = client.post(f"/api/v1/institutional-pilot/reports/{report['id']}/publish", headers=mod.HEADERS, json={"file_uri":"s3://synthetic/SYNTH-PILOT-REPORT-001.json","sha256":"d"*64}).json()
dashboard = client.get("/api/v1/institutional-pilot/dashboard", headers=mod.HEADERS).json()
result = {
    "backend_version":"1.4.0",
    "mode":"Synthetic",
    "run_status":completion.json().get("status"),
    "session_execution_id":execution_id,
    "metric_status":metric.get("status"),
    "report_status":published.get("status"),
    "verified_identities":dashboard.get("verified_identities"),
    "completed_sessions":dashboard.get("completed_sessions"),
    "adoption_events":dashboard.get("adoption_events"),
    "feedback_count":dashboard.get("feedback_count"),
    "published_reports":dashboard.get("published_reports"),
    "guardrail":dashboard.get("guardrail"),
    "institutional_claim":False,
}
out = ROOT / "reports/sprint13_institutional_pilot_smoke.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
print(out)
