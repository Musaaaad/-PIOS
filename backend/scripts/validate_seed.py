import sys
from pathlib import Path as _Path
ROOT_PATH = _Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path: sys.path.insert(0, str(ROOT_PATH))
import json
from pathlib import Path
from app.schemas.imports import BaselinePayload
from app.services.import_baseline import validate_baseline

path = Path(__file__).resolve().parents[1] / "seeds" / "PIOS_MVP_Import_Data_v1.json"
payload = BaselinePayload.model_validate(json.loads(path.read_text(encoding="utf-8")))
result = validate_baseline(payload)
print(result.model_dump_json(indent=2))
if not result.valid:
    raise SystemExit(1)
