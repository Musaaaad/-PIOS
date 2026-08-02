import json
import os
import tempfile
from pathlib import Path
import pytest

os.environ["PIOS_ENV"] = "test"
os.environ["PIOS_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["PIOS_ALLOW_DEV_TOKENS"] = "true"

# Isolate every filesystem root the app can write to during tests so a test
# run never mutates the committed evidence/report artifacts under backend/var/.
_TEST_VAR_ROOT = Path(tempfile.mkdtemp(prefix="pios_test_var_"))
os.environ["PIOS_OBJECT_STORAGE_ROOT"] = str(_TEST_VAR_ROOT / "evidence")
os.environ["PIOS_EXPORT_STORAGE_ROOT"] = str(_TEST_VAR_ROOT / "exports")
os.environ["PIOS_BACKUP_STORAGE_ROOT"] = str(_TEST_VAR_ROOT / "backups")
os.environ["PIOS_DEPLOYMENT_REPORT_ROOT"] = str(_TEST_VAR_ROOT / "deployment-reports")
os.environ["PIOS_BASELINE_RELEASE_ROOT"] = str(_TEST_VAR_ROOT / "baseline-releases")
os.environ["PIOS_GOVERNANCE_EXPORT_ROOT"] = str(_TEST_VAR_ROOT / "governance-exports")

from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.main import app
from app.schemas.imports import BaselinePayload
from app.services.seed import seed_baseline

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    payload = BaselinePayload.model_validate(json.loads((ROOT / "seeds/PIOS_MVP_Import_Data_v1.json").read_text(encoding="utf-8")))
    with SessionLocal() as db:
        seed_baseline(db, payload)
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def baseline_payload():
    return json.loads((ROOT / "seeds/PIOS_MVP_Import_Data_v1.json").read_text(encoding="utf-8"))
