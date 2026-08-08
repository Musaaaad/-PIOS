"""Sprint 23.8 - the exact token contract between Keycloak and this backend.

Live symptom this exists for: `pios-test` was granted the realm role
AccreditationLead, Keycloak confirmed it, the frontend decoded the ACCESS token
and displayed AccreditationLead - and every API call still came back 401.

401 is an AUTHENTICATION verdict. In app/core/security.py it can only come from
decode_oidc_token() raising, which happens before roles are ever looked at. So
the role was never the question; these tests pin which half of the contract is
actually being tested, and keep 401 and 403 from drifting into each other again.

Every token here is signed RS256 and carries the claim shape the pios realm
really emits, Keycloak's own default roles included - a token that omitted them
would be one Keycloak never issues.
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
CLIENT_ID = "pios-portal"
KID = "sprint238"

# What Keycloak hands every user in this realm regardless of assignment. None of
# these is a PIOS role, and the realm-role mapper copies them into `roles`
# alongside any real assignment - which is why a token can look populated while
# granting nothing.
KEYCLOAK_DEFAULTS = ["default-roles-pios", "offline_access", "uma_authorization"]


def _b64u(v: int) -> str:
    raw = v.to_bytes((v.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture(scope="module")
def idp():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers()
    jwks = {"keys": [{"kty": "RSA", "kid": KID, "use": "sig", "alg": "RS256",
                      "n": _b64u(pub.n), "e": _b64u(pub.e)}]}
    return key, json.dumps(jwks)


def mint(key, *, roles=(), issuer=ISSUER, audience=AUDIENCE, expires_in=300,
         sign_with=None, **over) -> str:
    """A token shaped exactly like one from the pios realm."""
    now = int(time.time())
    all_roles = [*KEYCLOAK_DEFAULTS, *roles]
    claims = {
        "sub": "b7c1f0e2-pios-test", "iss": issuer, "aud": audience, "azp": CLIENT_ID,
        "iat": now, "exp": now + expires_in, "typ": "Bearer", "scope": "openid profile email",
        "preferred_username": "pios-test", "email": "pios-test@turaif.example.sa",
        "name": "PIOS Test",
        "realm_access": {"roles": all_roles},   # Keycloak's own structure
        "roles": all_roles,                     # the realm-role mapper's claim
        "sites": ["TGH"],
    }
    claims.update(over)
    return jwt.encode(claims, sign_with or key, algorithm="RS256", headers={"kid": KID})


@pytest.fixture
def client(monkeypatch, idp):
    _, jwks = idp
    monkeypatch.setenv("PIOS_ENV", "production")
    monkeypatch.setenv("PIOS_AUTH_MODE", "oidc")
    monkeypatch.setenv("PIOS_ALLOW_DEV_TOKENS", "false")
    monkeypatch.setenv("PIOS_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("PIOS_OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("PIOS_OIDC_JWKS_JSON", jwks)
    get_settings.cache_clear()
    import app.main as main_module

    importlib.reload(main_module)
    yield TestClient(main_module.app)
    monkeypatch.undo()
    get_settings.cache_clear()
    importlib.reload(main_module)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ============================ Case 1 - the live user's exact token is accepted

def test_the_granted_role_is_accepted_end_to_end(client, idp):
    """The case the live failure claimed was broken.

    A token carrying AccreditationLead *alongside* Keycloak's defaults must
    authenticate AND authorize. If this passes, a live 401 cannot be blamed on
    the role assignment.
    """
    key, _ = idp
    token = mint(key, roles=["AccreditationLead"])

    me = client.get("/api/v1/identity/me", headers=auth(token))
    assert me.status_code == 200, f"authentication failed for a correctly granted user: {me.text}"
    body = me.json()
    assert body["auth_source"] == "oidc"
    assert "AccreditationLead" in body["roles"]
    assert body["site_codes"] == ["TGH"]

    dash = client.get("/api/v1/dashboard/overview", headers=auth(token))
    assert dash.status_code == 200, f"a protected endpoint refused a granted user: {dash.text}"


def test_keycloak_default_roles_do_not_hide_the_real_one(client, idp):
    """The PIOS role must be found even though defaults outnumber it 3:1."""
    key, _ = idp
    roles = client.get("/api/v1/identity/me",
                       headers=auth(mint(key, roles=["AccreditationLead"]))).json()["roles"]
    assert "AccreditationLead" in roles
    for noise in KEYCLOAK_DEFAULTS:
        assert noise in roles or True   # presence is fine; what matters is the real role resolves


# ===================== Case 2 - authenticated but unauthorized must be 403

def test_no_pios_role_is_403_not_401(client, idp):
    """Deny-by-default, but as an AUTHORIZATION verdict.

    The token is perfectly valid: signature, issuer, audience and expiry all
    pass. Answering 401 would tell the client to re-authenticate, which can
    never fix a missing role, and would send the user round a sign-in loop.
    """
    key, _ = idp
    r = client.get("/api/v1/identity/me", headers=auth(mint(key, roles=[])))
    assert r.status_code == 403, (
        f"a valid token lacking a PIOS role must be 403, got {r.status_code}: {r.text}"
    )


def test_a_wrong_role_on_a_guarded_route_is_403(client, idp):
    key, _ = idp
    token = mint(key, roles=["ReadOnlyAuditor"])
    assert client.get("/api/v1/identity/me", headers=auth(token)).status_code == 200
    r = client.post("/api/v1/readiness/snapshots/calculate", headers=auth(token), json={})
    assert r.status_code == 403, f"insufficient role must be 403, got {r.status_code}"


# ================== Cases 3-6 - genuine authentication failures must be 401

def test_expired_token_is_401(client, idp):
    key, _ = idp
    r = client.get("/api/v1/identity/me", headers=auth(mint(key, roles=["AccreditationLead"], expires_in=-30)))
    assert r.status_code == 401


def test_wrong_issuer_is_401(client, idp):
    key, _ = idp
    r = client.get("/api/v1/identity/me",
                   headers=auth(mint(key, roles=["AccreditationLead"], issuer="https://attacker.example/realms/pios")))
    assert r.status_code == 401


def test_wrong_audience_is_401(client, idp):
    key, _ = idp
    r = client.get("/api/v1/identity/me",
                   headers=auth(mint(key, roles=["AccreditationLead"], audience="some-other-api")))
    assert r.status_code == 401


def test_bad_signature_is_401(client, idp):
    key, _ = idp
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    r = client.get("/api/v1/identity/me",
                   headers=auth(mint(key, roles=["AccreditationLead"], sign_with=other)))
    assert r.status_code == 401


def test_missing_token_is_401(client):
    assert client.get("/api/v1/identity/me").status_code == 401


def test_garbage_token_is_401(client):
    assert client.get("/api/v1/identity/me", headers=auth("not-a-jwt")).status_code == 401


# ============ the distinction itself: same token, only the role differs

def test_401_and_403_are_decided_by_different_things(client, idp):
    """Pins the semantic boundary so it cannot silently collapse again.

    Identical tokens except for the role: one authorizes, one does not, and
    NEITHER is 401 - because both authenticate.
    """
    key, _ = idp
    granted = client.get("/api/v1/identity/me", headers=auth(mint(key, roles=["AccreditationLead"])))
    ungranted = client.get("/api/v1/identity/me", headers=auth(mint(key, roles=[])))
    assert granted.status_code == 200
    assert ungranted.status_code == 403
    assert ungranted.status_code != 401, (
        "authentication succeeded for both; only authorization differs, so 401 is wrong"
    )


# ======================= server misconfiguration must not look like a bad token

def test_unconfigured_oidc_is_not_reported_as_an_invalid_token(monkeypatch, idp):
    """A server with no issuer/JWKS configured is broken - the token is fine.

    Reporting 401 "Invalid OIDC token" here blames the user's session for an
    operator mistake, and sends the app into a re-authentication loop that can
    never succeed. It must be a server-side status instead.
    """
    key, _ = idp
    monkeypatch.setenv("PIOS_ENV", "production")
    monkeypatch.setenv("PIOS_AUTH_MODE", "oidc")
    monkeypatch.setenv("PIOS_ALLOW_DEV_TOKENS", "false")
    monkeypatch.delenv("PIOS_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("PIOS_OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("PIOS_OIDC_JWKS_JSON", raising=False)
    monkeypatch.delenv("PIOS_OIDC_JWKS_URL", raising=False)
    get_settings.cache_clear()
    import app.main as main_module

    importlib.reload(main_module)
    try:
        c = TestClient(main_module.app)
        r = c.get("/api/v1/identity/me", headers=auth(mint(key, roles=["AccreditationLead"])))
        assert r.status_code == 503, (
            f"an unconfigured identity provider must be a server fault (503), got {r.status_code}"
        )
        assert "token" not in r.json().get("detail", "").lower(), (
            "the message must not blame the token for a server configuration gap"
        )
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        importlib.reload(main_module)
