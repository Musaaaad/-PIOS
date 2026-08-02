from __future__ import annotations
import sys
from pathlib import Path as _Path
ROOT_PATH = _Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path: sys.path.insert(0, str(ROOT_PATH))
import json, os
from pathlib import Path

os.environ.setdefault("PIOS_ENV", "test")
os.environ.setdefault("PIOS_DATABASE_URL", "sqlite+pysqlite:///:memory:")

from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.main import app
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline

ROOT = Path(__file__).resolve().parents[1]
Base.metadata.create_all(engine)
payload = BaselinePayload.model_validate(json.loads((ROOT / "seeds/PIOS_MVP_Import_Data_v1.json").read_text(encoding="utf-8")))
with SessionLocal() as db:
    totals = seed_baseline(db, payload)

client = TestClient(app)
checks = {}
checks["health"] = client.get("/health").status_code == 200
checks["ready"] = client.get("/ready").status_code == 200
checks["standards_41"] = len(client.get("/api/v1/standards").json()) == 41
checks["me_266"] = len(client.get("/api/v1/measurable-elements").json()) == 266
workspace = client.get("/api/v1/measurable-elements/MM.5.2/workspace").json()
checks["mm_5_2_nested_9"] = workspace["workspace_state"]["nested_clause_count"] == 9
checks["documents_75"] = len(client.get("/api/v1/documents?limit=100").json()) == 75
result = {"valid": all(checks.values()), "totals": totals, "checks": checks}
out = ROOT / "reports" / "sqlite_integration_smoke.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
if not result["valid"]:
    raise SystemExit(1)
