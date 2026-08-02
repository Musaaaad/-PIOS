import json, os, sys
from datetime import date, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
os.environ.setdefault("PIOS_ENV", "test")
os.environ.setdefault("PIOS_DATABASE_URL", "sqlite+pysqlite:///:memory:")

from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.main import app
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline

Base.metadata.create_all(engine)
with SessionLocal() as db:
    payload = BaselinePayload.model_validate(json.loads((ROOT / "seeds/PIOS_MVP_Import_Data_v1.json").read_text()))
    seed_baseline(db, payload)
client = TestClient(app)

finding = client.post("/api/v1/findings", json={
    "me_id":"MM.31.1", "criterion":"Dispensing workflow control", "severity":"P1",
    "problem_statement":"A verified dispensing workflow gap requires corrective action.",
    "owner_role_code":"MEOwner", "due_date":str(date.today()+timedelta(days=30))
}).json()
capa = client.post(f"/api/v1/findings/{finding['id']}/capas", json={
    "title":"Close dispensing workflow gap", "owner_role_code":"CAPAOwner", "verifier_role_code":"CAPAVerifier",
    "due_date":str(date.today()+timedelta(days=30)), "root_cause":"The workflow had no controlled verification gate.",
    "action_plan":"Configure the control, train users and verify effectiveness."
}).json()
action = client.post(f"/api/v1/capas/{capa['id']}/actions", json={
    "action":"Configure and train the controlled workflow.", "owner_role_code":"CAPAOwner", "due_date":str(date.today()+timedelta(days=10))
}).json()
client.post(f"/api/v1/capas/{capa['id']}/submit", json={})
client.post(f"/api/v1/capas/{capa['id']}/approve", json={})
client.patch(f"/api/v1/capa-actions/{action['id']}", json={"status":"Completed","completion_note":"Control configured and training completed."})
client.post(f"/api/v1/capas/{capa['id']}/implementation/complete", json={})
check = client.post(f"/api/v1/capas/{capa['id']}/effectiveness-checks", json={
    "method":"Repeat a representative dispensing tracer.", "target":"100% adherence", "due_date":str(date.today()+timedelta(days=14)), "sample_size":20
}).json()
client.post(f"/api/v1/effectiveness-checks/{check['id']}/complete", json={"result":"Target met in 20/20 cases.","effective":True})
closed = client.post(f"/api/v1/capas/{capa['id']}/close", json={"comment":"Independent check passed."}).json()
snapshot = client.post("/api/v1/readiness/snapshots/calculate", json={"period_label":"Sprint 3 smoke"}).json()
result = {"finding": finding["id"], "capa": capa["id"], "capa_status": closed["status"], "readiness_score": snapshot["readiness_score"], "overall_status": snapshot["overall_status"], "snapshot_items": len(client.get(f"/api/v1/readiness/snapshots/{snapshot['id']}").json()["items"])}
out = ROOT / "reports/capa_readiness_smoke.json"
out.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(out); print(json.dumps(result, indent=2))
