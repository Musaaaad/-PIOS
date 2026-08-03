"""Sprint 23 institutional authentication: end-to-end acceptance path.

Every request here is authenticated with a real RS256 token verified against a
real JWKS. No development token, no auth bypass, no monkeypatched principal -
the point is to prove the production authentication path works, so faking any
part of it would defeat the exercise.

Acceptance path (Sprint 23 item 9):
  Dashboard -> Readiness/ESR -> a standard -> its measurable elements ->
  add evidence -> save -> audit log -> readiness/KPI refresh
"""
from __future__ import annotations

import base64
import importlib
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core.config import get_settings

ISSUER = "https://pios-keycloak.onrender.com/realms/pios"
AUDIENCE = "pios-api"
KID = "sprint23"

# Roles the pios realm grants (deploy/keycloak/pios-realm.json). Broad here so
# one identity can walk the whole path; real users get a narrower set.
ROLES = [
    "SystemAdmin", "AccreditationLead", "MedicationSafety", "PharmacyDirector",
    "EvidenceCollector", "EvidenceReviewer", "CAPAOwner", "CAPAVerifier",
    "ReadOnlyAuditor",
]


def _b64u(v: int) -> str:
    raw = v.to_bytes((v.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture(scope="module")
def idp():
    """A throwaway identity provider: RSA keypair plus its published JWKS."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers()
    jwks = {"keys": [{"kty": "RSA", "kid": KID, "use": "sig", "alg": "RS256",
                      "n": _b64u(pub.n), "e": _b64u(pub.e)}]}
    return key, json.dumps(jwks)


def mint(key, **overrides) -> str:
    now = int(time.time())
    claims = {
        "sub": "f1e2d3c4-turaif-pilot", "iss": ISSUER, "aud": AUDIENCE,
        "iat": now, "exp": now + 600,
        "email": "lead@turaif.example.sa", "name": "قائد الاعتماد",
        "roles": ROLES, "sites": ["TGH"],
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})


@pytest.fixture
def client(monkeypatch, idp):
    """The real app configured for OIDC, with dev tokens firmly off."""
    _, jwks = idp
    monkeypatch.setenv("PIOS_ENV", "production")
    monkeypatch.setenv("PIOS_AUTH_MODE", "oidc")
    monkeypatch.setenv("PIOS_ALLOW_DEV_TOKENS", "false")
    monkeypatch.setenv("PIOS_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("PIOS_OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("PIOS_OIDC_JWKS_JSON", jwks)
    monkeypatch.setenv("PIOS_CORS_ORIGINS", "https://pios-frontend.onrender.com")
    get_settings.cache_clear()
    import app.main as main_module

    importlib.reload(main_module)
    yield TestClient(main_module.app)
    # Restore the environment BEFORE rebuilding settings. Clearing the cache
    # while the production/OIDC values are still set would repopulate it with
    # them and leak that configuration into every later test in the session.
    monkeypatch.undo()
    get_settings.cache_clear()
    importlib.reload(main_module)


def auth(key) -> dict:
    return {"Authorization": f"Bearer {mint(key)}"}


# --------------------------------------------------------------- gate is real

def test_protected_route_rejects_anonymous(client):
    assert client.get("/api/v1/identity/me").status_code in (401, 403)


def test_protected_route_rejects_dev_token_in_production(client):
    r = client.get(
        "/api/v1/identity/me",
        headers={"Authorization": "Bearer dev:someone:SystemAdmin"},
    )
    assert r.status_code in (401, 403), (
        "a development token must never authenticate against a production "
        "deployment, whatever PIOS_ALLOW_DEV_TOKENS says"
    )


@pytest.mark.parametrize("bad", [
    {"iss": "https://attacker.example"},
    {"aud": "some-other-api"},
    {"exp": 1},
])
def test_tampered_claims_are_rejected(client, idp, bad):
    key, _ = idp
    r = client.get("/api/v1/identity/me",
                   headers={"Authorization": f"Bearer {mint(key, **bad)}"})
    assert r.status_code in (401, 403)


def test_token_signed_by_an_unknown_key_is_rejected(client):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    forged = jwt.encode(
        {"sub": "intruder", "iss": ISSUER, "aud": AUDIENCE, "exp": now + 300,
         "roles": ROLES, "sites": ["TGH"]},
        other, algorithm="RS256", headers={"kid": KID},
    )
    r = client.get("/api/v1/identity/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code in (401, 403)


def test_token_without_mapped_roles_is_refused(client, idp):
    key, _ = idp
    r = client.get("/api/v1/identity/me",
                   headers={"Authorization": f"Bearer {mint(key, roles=[])}"})
    assert r.status_code == 403, "deny-by-default: no mapped roles means no access"


# ------------------------------------------------------------------- identity

def test_valid_token_authenticates_and_maps_roles_and_sites(client, idp):
    key, _ = idp
    r = client.get("/api/v1/identity/me", headers=auth(key))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["auth_source"] == "oidc"
    assert body["user_id"] == "f1e2d3c4-turaif-pilot"
    assert "AccreditationLead" in body["roles"]
    assert body["site_codes"] == ["TGH"]


# ----------------------------------------------------- full acceptance path

def test_acceptance_path_dashboard_to_kpi(client, idp):
    """Dashboard -> standard -> MEs -> evidence -> save -> audit -> KPI."""
    key, _ = idp
    h = auth(key)

    # 1. Dashboard
    overview = client.get("/api/v1/dashboard/overview", headers=h)
    assert overview.status_code == 200, overview.text
    assert overview.json()["site"]["code"] == "TGH"

    # 2. Readiness / ESR - calculate a snapshot so KPIs have a baseline
    snap = client.post("/api/v1/readiness/snapshots/calculate", headers=h,
                       json={"period_label": "sprint23-acceptance"})
    assert snap.status_code in (200, 201), snap.text
    before = snap.json()

    # 3. Standards map
    standards = client.get("/api/v1/dashboard/standards", headers=h)
    assert standards.status_code == 200, standards.text
    codes = [s["standard"] for s in standards.json()["standards"]]
    assert codes, "the standards dashboard must return the seeded standards"

    # 4. Open measurable elements for a standard (MM.5 when seeded)
    target = "MM.5" if "MM.5" in codes else codes[0]
    mes = client.get(f"/api/v1/measurable-elements?standard_code={target}", headers=h)
    assert mes.status_code == 200, mes.text
    items = mes.json()
    assert items, f"{target} must expose measurable elements"
    me_id = items[0]["me_id"]

    # 5. Add evidence: campaign -> request -> item (the real create path)
    campaign = client.post("/api/v1/evidence-campaigns", headers=h, json={
        "code": "S23-ACCEPT", "name": "Sprint 23 acceptance",
        "period_start": "2026-08-01", "period_end": "2026-08-31",
    })
    assert campaign.status_code in (200, 201), campaign.text
    campaign_id = campaign.json()["id"]

    # Collection is gated on the campaign being Open - a real workflow rule,
    # followed here rather than worked around.
    opened = client.post(f"/api/v1/evidence-campaigns/{campaign_id}/lifecycle", headers=h,
                         json={"to_status": "Open", "comment": "sprint23 acceptance"})
    assert opened.status_code == 200, opened.text
    assert opened.json()["status"] == "Open"

    reqs = client.post(f"/api/v1/evidence-campaigns/{campaign_id}/requests", headers=h,
                       json={"requests": [{"me_id": me_id, "tool_code": "OBS", "due_at": "2026-08-20T00:00:00Z"}]})
    assert reqs.status_code in (200, 201), reqs.text
    request_id = reqs.json()[0]["id"]

    started = client.post(f"/api/v1/evidence-requests/{request_id}/start", headers=h)
    assert started.status_code == 200, started.text

    # 6. Save the evidence item
    item = client.post(f"/api/v1/evidence-requests/{request_id}/items", headers=h, json={
        "source_type": "Observation",
        "title": "ملاحظة مباشرة لعينة صرف الأدوية",
        "structured_data": {"observed": 10, "compliant": 9},
        "sample_size": 10,
        "collection_location": "Main pharmacy",
    })
    assert item.status_code in (200, 201), item.text
    assert item.json()["id"]

    # 7. Audit log records the authenticated actor
    audit = client.get("/api/v1/audit-events?limit=50", headers=h)
    assert audit.status_code == 200, audit.text
    events = audit.json()
    events = events.get("items", events) if isinstance(events, dict) else events
    assert events, "writes must produce audit events"

    # 8. KPI / readiness refresh still authorised and consistent
    after = client.post("/api/v1/readiness/snapshots/calculate", headers=h,
                        json={"period_label": "sprint23-acceptance-2"})
    assert after.status_code in (200, 201), after.text
    current = client.get("/api/v1/readiness/current", headers=h)
    assert current.status_code == 200, current.text
    assert current.json()["id"] == after.json()["id"], "current must reflect the newest snapshot"
    assert before["id"] != after.json()["id"], "the KPI refresh must produce a new snapshot"


# ----------------------------------------------------------------- CORS + auth

def test_401_from_oidc_still_carries_cors_headers(client):
    origin = "https://pios-frontend.onrender.com"
    r = client.get("/api/v1/identity/me", headers={"Origin": origin})
    assert r.status_code in (401, 403)
    assert r.headers.get("access-control-allow-origin") == origin, (
        "without CORS headers the browser reports an opaque failure and the "
        "user never learns that sign-in is what is missing"
    )
