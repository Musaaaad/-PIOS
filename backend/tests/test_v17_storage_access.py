import hashlib
from io import BytesIO
from pathlib import Path
import pytest
from fastapi import HTTPException, UploadFile
from app.core.config import get_settings
from app.core.security import Principal
from app.core.site_access import require_site_access, scoped_evidence_prefix
from app.services.evidence_storage import store_upload, local_path_from_uri

def configure_local(monkeypatch, tmp_path):
    monkeypatch.setenv("PIOS_ENV", "test")
    monkeypatch.setenv("PIOS_OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("PIOS_OBJECT_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("PIOS_ANTIVIRUS_MODE", "basic")
    get_settings.cache_clear()

def test_upload_download_hash_and_scoped_key(monkeypatch, tmp_path):
    configure_local(monkeypatch, tmp_path)
    payload=b"PIOS evidence integration v1.7"
    upload=UploadFile(filename="evidence.txt", file=BytesIO(payload), headers={"content-type":"text/plain"})
    stored=store_upload(upload, scoped_evidence_prefix("TGH", "REQ-001"))
    path=local_path_from_uri(stored.storage_uri)
    assert path and path.read_bytes()==payload
    assert stored.sha256==hashlib.sha256(payload).hexdigest()
    assert "/sites/TGH/evidence/REQ-001/" in stored.storage_uri

def test_cross_site_access_denied():
    principal=Principal("u1", frozenset({"EvidenceOwner"}), site_codes=frozenset({"TGH"}), auth_source="oidc")
    require_site_access(principal, "TGH")
    with pytest.raises(HTTPException) as exc: require_site_access(principal, "ARH")
    assert exc.value.status_code==403

def test_system_admin_cross_site_allowed():
    principal=Principal("admin", frozenset({"SystemAdmin"}), site_codes=frozenset(), auth_source="oidc")
    require_site_access(principal, "ARH")

def test_unsafe_scope_rejected():
    with pytest.raises(ValueError): scoped_evidence_prefix("../", "REQ")

def test_eicar_rejected(monkeypatch, tmp_path):
    configure_local(monkeypatch, tmp_path)
    upload=UploadFile(filename="bad.txt", file=BytesIO(b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"), headers={"content-type":"text/plain"})
    with pytest.raises(HTTPException) as exc: store_upload(upload, scoped_evidence_prefix("TGH","REQ-2"))
    assert exc.value.status_code==422
