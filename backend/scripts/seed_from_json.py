import sys
from pathlib import Path as _Path
ROOT_PATH = _Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path: sys.path.insert(0, str(ROOT_PATH))
import json
from pathlib import Path
from app.db.session import SessionLocal
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline

path = Path(__file__).resolve().parents[1] / "seeds" / "PIOS_MVP_Import_Data_v1.json"
payload = BaselinePayload.model_validate(json.loads(path.read_text(encoding="utf-8")))
with SessionLocal() as session:
    totals = seed_baseline(session, payload)
print(totals)
