import json, os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("PIOS_ENV", "test")
os.environ.setdefault("PIOS_DATABASE_URL", "sqlite+pysqlite:///./var/sprint8-smoke.db")
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

c = TestClient(app)
h = {"Authorization":"Bearer dev:smoke:SystemAdmin,AccreditationLead,MedicationSafety,EvidenceReviewer,MEOwner,PharmacyDirector"}
boot = c.post("/api/v1/assurance/programs/bootstrap-p0", headers=h).json()
due = datetime.now(timezone.utc) + timedelta(days=14)
cycle = c.post(f"/api/v1/assurance/programs/{boot['program']['id']}/cycles", headers=h, json={"code":"SPRINT8-Q3","period_label":"2026-Q3","due_at":due.isoformat()}).json()
detail = c.get(f"/api/v1/assurance/cycles/{cycle['id']}", headers=h).json()
first = detail["tasks"][0]
c.post(f"/api/v1/assurance/tasks/{first['id']}/complete", headers=h, json={"result":"Fail","comment":"Smoke-test recurring control failure"})
for task in detail["tasks"][1:]:
    c.post(f"/api/v1/assurance/tasks/{task['id']}/complete", headers=h, json={"result":"Pass","evidence_reference":f"smoke:{task['me_id']}"})
closed = c.post(f"/api/v1/assurance/cycles/{cycle['id']}/close", headers=h).json()
dq = c.post("/api/v1/assurance/data-quality/runs", headers=h, json={"code":"SPRINT8-DQ"}).json()
wave = c.post("/api/v1/assurance/rollout-waves", headers=h, json={"code":"SPRINT8-WAVE","name":"Sprint 8 smoke rollout wave","planned_start":date(2026,9,1).isoformat(),"planned_end":date(2026,12,31).isoformat()}).json()
site = c.post(f"/api/v1/assurance/rollout-waves/{wave['id']}/sites", headers=h, json={"site_code":"SMK","name_ar":"موقع تجربة","name_en":"Smoke Site","site_type":"Hospital"}).json()
ready = c.patch(f"/api/v1/assurance/rollout-wave-sites/{site['id']}/gates", headers=h, json={"baseline_imported":True,"users_ready":True,"training_complete":True,"deployment_pass":True,"oidc_pass":True,"evidence_reference":"smoke:rollout"}).json()
report = {
    "scope":"local-build-verification-only",
    "institutional_readiness":False,
    "program_controls":boot["total"],
    "cycle_tasks":len(detail["tasks"]),
    "cycle_status":closed["status"],
    "cycle_summary":closed["summary_json"],
    "data_quality":dq["summary_json"],
    "rollout_site_ready":ready["go_live_ready"],
}
(ROOT / "reports/sprint8_assurance_smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
