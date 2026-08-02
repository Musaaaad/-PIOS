from __future__ import annotations
import sys
from pathlib import Path as _Path
ROOT_PATH = _Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path: sys.path.insert(0, str(ROOT_PATH))
import json
from pathlib import Path
from sqlalchemy import text, select, func
from app.db.session import SessionLocal
from app.models.entities import Standard, MeasurableElement, NestedClause, Document

checks = {}
with SessionLocal() as db:
    version = db.scalar(text("select version()"))
    checks["database"] = version
    checks["standards"] = db.scalar(select(func.count()).select_from(Standard))
    checks["measurable_elements"] = db.scalar(select(func.count()).select_from(MeasurableElement))
    checks["nested_clauses"] = db.scalar(select(func.count()).select_from(NestedClause))
    checks["documents"] = db.scalar(select(func.count()).select_from(Document))
checks["valid"] = (
    checks["standards"] == 41 and checks["measurable_elements"] == 266
    and checks["nested_clauses"] == 63 and checks["documents"] == 75
)
out = Path(__file__).resolve().parents[1] / "reports" / "postgres_runtime_smoke.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(checks, ensure_ascii=False, indent=2))
if not checks["valid"]:
    raise SystemExit(1)
