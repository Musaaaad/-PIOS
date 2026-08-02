import json
from pathlib import Path
from app.schemas.imports import BaselinePayload
from app.services.import_baseline import validate_baseline


def test_baseline_counts_and_esr():
    path = Path(__file__).resolve().parents[1] / "seeds" / "PIOS_MVP_Import_Data_v1.json"
    payload = BaselinePayload.model_validate(json.loads(path.read_text(encoding="utf-8")))
    result = validate_baseline(payload)
    assert result.valid, result.errors
    assert result.totals == {"measurable_elements": 266, "nested_clauses": 63, "documents": 75}
    assert any(w["code"] == "DOCUMENT_CODE_DUPLICATE" for w in result.warnings)
