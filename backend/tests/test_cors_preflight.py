"""CORS preflight and header-propagation tests.

Motivated by a live defect: the frontend reported Safari's "Load failed" with no
HTTP status, which is what a browser shows when a response is blocked by the
same-origin policy. The application's CORS configuration was correct, but any
response generated *outside* CORSMiddleware - notably the default 500 from an
unhandled exception - carried no Access-Control-Allow-Origin, so a backend fault
was indistinguishable from a CORS misconfiguration.

These tests pin both halves: the preflight contract, and the rule that every
response class (200, 401, 422, 500) keeps its CORS headers.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings

ORIGIN = "https://pios-frontend.onrender.com"
PAGES = "https://musaaaad.github.io"
ENDPOINT = "/api/v1/readiness/snapshots/calculate"
BROWSER_HEADERS = "content-type,authorization,x-trace-id,idempotency-key"


def build_client(monkeypatch, origins: str) -> TestClient:
    """Rebuild the real app with a given PIOS_CORS_ORIGINS value."""
    monkeypatch.setenv("PIOS_CORS_ORIGINS", origins)
    get_settings.cache_clear()
    import app.main as main_module

    importlib.reload(main_module)
    return TestClient(main_module.app)


@pytest.fixture(autouse=True)
def _restore_app():
    yield
    get_settings.cache_clear()
    import app.main as main_module

    importlib.reload(main_module)


# --------------------------------------------------------------- normalisation
# An Origin header is always a bare scheme://host[:port]. CORSMiddleware compares
# it literally, so a configured trailing slash matches nothing and silently
# breaks every browser request.

@pytest.mark.parametrize(
    "configured,expected",
    [
        (ORIGIN, [ORIGIN]),
        (f"{ORIGIN}/", [ORIGIN]),
        (f"  {ORIGIN}/  ", [ORIGIN]),
        (f"{ORIGIN},{PAGES}", [ORIGIN, PAGES]),
        (f"{ORIGIN}/ , {PAGES}/ ", [ORIGIN, PAGES]),
        (f"{ORIGIN},{ORIGIN}", [ORIGIN]),
        (f"{ORIGIN},,{PAGES}", [ORIGIN, PAGES]),
    ],
)
def test_origins_are_normalised(configured, expected):
    assert Settings(cors_origins=configured).cors_origin_list == expected


def test_invalid_origins_are_rejected_and_reported():
    s = Settings(cors_origins=f"bad-origin,{ORIGIN},ftp://x.example")
    assert s.cors_origin_list == [ORIGIN]
    assert set(s.cors_origin_problems()) == {"bad-origin", "ftp://x.example"}


def test_wildcard_is_preserved():
    assert Settings(cors_origins="*").cors_origin_list == ["*"]


# -------------------------------------------------------------------- preflight

def test_preflight_succeeds_with_all_browser_headers(monkeypatch):
    client = build_client(monkeypatch, ORIGIN)
    r = client.options(
        ENDPOINT,
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": BROWSER_HEADERS,
        },
    )
    assert r.status_code in (200, 204), r.text
    assert r.headers["access-control-allow-origin"] == ORIGIN

    allowed_methods = r.headers["access-control-allow-methods"]
    assert "POST" in allowed_methods

    allowed = {h.strip().lower() for h in r.headers["access-control-allow-headers"].split(",")}
    for required in ("content-type", "authorization", "x-trace-id", "idempotency-key"):
        assert required in allowed, f"{required} missing from {allowed}"


def test_preflight_works_when_origin_configured_with_trailing_slash(monkeypatch):
    client = build_client(monkeypatch, f"{ORIGIN}/")
    r = client.options(
        ENDPOINT,
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": BROWSER_HEADERS,
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers["access-control-allow-origin"] == ORIGIN


def test_both_render_and_pages_origins_are_allowed(monkeypatch):
    client = build_client(monkeypatch, f"{ORIGIN}, {PAGES}")
    for origin in (ORIGIN, PAGES):
        r = client.options(
            ENDPOINT,
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": BROWSER_HEADERS,
            },
        )
        assert r.status_code in (200, 204)
        assert r.headers["access-control-allow-origin"] == origin


def test_unlisted_origin_is_not_granted_access(monkeypatch):
    client = build_client(monkeypatch, ORIGIN)
    r = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"


# ------------------------------------------------- headers survive every status

def test_401_response_still_carries_cors_headers(monkeypatch):
    monkeypatch.setenv("PIOS_ENV", "production")
    monkeypatch.setenv("PIOS_AUTH_MODE", "oidc")
    monkeypatch.setenv("PIOS_ALLOW_DEV_TOKENS", "false")
    client = build_client(monkeypatch, ORIGIN)
    r = client.post(ENDPOINT, headers={"Origin": ORIGIN}, json={})
    assert r.status_code in (401, 403), r.text
    assert r.headers.get("access-control-allow-origin") == ORIGIN, (
        "a 401 without CORS headers reaches the browser as an opaque "
        "'Load failed', hiding the real reason"
    )


def test_404_response_still_carries_cors_headers(monkeypatch):
    client = build_client(monkeypatch, ORIGIN)
    r = client.get("/api/v1/definitely-not-a-route", headers={"Origin": ORIGIN})
    assert r.status_code == 404
    assert r.headers.get("access-control-allow-origin") == ORIGIN


def test_unhandled_exception_returns_500_with_cors_headers(monkeypatch):
    """The regression this suite exists for.

    Starlette generates its default 500 in ServerErrorMiddleware, outside every
    user middleware including CORS, so before the middleware reorder this
    response had no Access-Control-Allow-Origin and Safari reported it as a
    same-origin failure rather than a server error.
    """
    client = build_client(monkeypatch, ORIGIN)
    import app.main as main_module

    @main_module.app.get("/__boom")
    def _boom():
        raise RuntimeError("intentional failure for CORS test")

    client = TestClient(main_module.app, raise_server_exceptions=False)
    r = client.get("/__boom", headers={"Origin": ORIGIN})
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    assert r.json()["code"] == "INTERNAL_ERROR"
    assert r.json()["trace_id"], "the 500 must carry a trace id for log correlation"


# ------------------------------------------------------------------ diagnostics

def test_diagnostics_endpoint_proves_active_configuration(monkeypatch):
    client = build_client(monkeypatch, f"{ORIGIN}/ ,bad-origin")
    body = client.get("/__diagnostics/cors").json()
    assert body["allowed_origins"] == [ORIGIN]
    assert body["rejected_entries"] == ["bad-origin"]
    assert "POST" in body["allow_methods"]
    assert body["raw_configured_value_present"] is True


def test_diagnostics_endpoint_exposes_no_secrets(monkeypatch):
    client = build_client(monkeypatch, ORIGIN)
    raw = client.get("/__diagnostics/cors").text.lower()
    for forbidden in ("password", "secret", "token", "postgres://", "postgresql", "jwks"):
        assert forbidden not in raw, f"diagnostics leaked {forbidden!r}"
