import os, tempfile, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("PIOS_ENV", "test")
os.environ.setdefault("PIOS_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("PIOS_OBJECT_STORAGE_BACKEND", "local")
os.environ.setdefault("PIOS_OBJECT_STORAGE_ROOT", tempfile.mkdtemp(prefix="pios-evidence-smoke-"))

from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.main import app
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline
import json

Base.metadata.create_all(engine)
with SessionLocal() as db:
    payload = BaselinePayload.model_validate(json.loads((ROOT / "seeds/PIOS_MVP_Import_Data_v1.json").read_text()))
    seed_baseline(db, payload)

client = TestClient(app)
c = client.post("/api/v1/evidence-campaigns", json={
    "name": "Smoke Campaign", "period_start": "2026-07-01", "period_end": "2026-09-30"
}).json()
client.post(f"/api/v1/evidence-campaigns/{c['id']}/lifecycle", json={"to_status": "Open"})
r = client.post(f"/api/v1/evidence-campaigns/{c['id']}/requests", json={"requests": [{
    "me_id": "MM.5.3", "tool_code": "ECF-O", "eoc": ["O", "I"]
}]}).json()[0]
client.post(f"/api/v1/evidence-requests/{r['id']}/start")
i = client.post(f"/api/v1/evidence-requests/{r['id']}/items", json={
    "source_type": "Observation", "title": "HAM tracer",
    "structured_data": {"sample": 10, "pass": 8}, "sample_size": 10,
    "scope_sites": ["TGH"], "scope_shifts": ["Day", "Night"]
}).json()
client.post(f"/api/v1/evidence-items/{i['id']}/submit")
client.post(f"/api/v1/evidence-items/{i['id']}/review/start")
codes = ["AUTHENTICITY","CURRENCY","SCOPE","REPRESENTATIVENESS","TRACEABILITY","CONSISTENCY","EOC_MATCH"]
review = client.post(f"/api/v1/evidence-items/{i['id']}/reviews", json={
    "verdict": "Partial", "reason_code": "SCOPE_GAP",
    "tests": [{"test_code": x, "result": "Fail" if x == "SCOPE" else "Pass"} for x in codes]
}).json()
result = {
    "campaign": c["id"], "request": r["id"], "item": i["id"],
    "evidence_status": review["evidence_status"], "finding_created": bool(review["finding_id"]),
    "workspace_started": client.get("/api/v1/measurable-elements/MM.5.3/workspace").json()["workspace_state"]["evidence_collection_started"],
}
out = ROOT / "reports/evidence_workflow_smoke.json"
out.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(out)
print(json.dumps(result, indent=2))
