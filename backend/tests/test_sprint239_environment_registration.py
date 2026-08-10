"""Sprint 23.9 follow-up - registering the deployment this service runs in.

Reported symptom: the acceptance screen said "no deployment environment is
registered" while pios-frontend, pios-api, pios-keycloak and pios-db were all
running on Render.

Both statements were true at once. "The services are up" is an observation
about processes; "an environment is registered" is a row in
deployment_environments that only exists once somebody records it. No seed, no
migration and no startup hook has ever created one - `grep DeploymentEnvironment(`
finds exactly one construction site, the create endpoint.

The fix wires three settings that were declared in Settings and read nowhere:
deployment_environment_code, tls_enabled and monitoring_enabled. Registration
reads what the operator declared through the service's own environment; it does
not infer. These tests pin the line between the two, because crossing it would
make a gate pass about a machine that is not this deployment.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import DeploymentEnvironment
from app.services.deployment_acceptance import ENVIRONMENT_TYPES, PROD_LIKE_TYPES

DECLARE = "/api/v1/deployment/environments/current/declaration"
REGISTER = "/api/v1/deployment/environments/register-current"
SUMMARY = "/api/v1/deployment/acceptance-summary"
EVALUATE = "/api/v1/deployment/acceptance-summary/evaluate"


@pytest.fixture
def render_like(monkeypatch):
    """The pios-api service as render.yaml configures it, fully declared."""
    monkeypatch.setenv("PIOS_DEPLOYMENT_ENVIRONMENT_TYPE", "Pilot")
    monkeypatch.setenv("PIOS_DEPLOYMENT_ENVIRONMENT_CODE", "render-pilot")
    monkeypatch.setenv("PIOS_DEPLOYMENT_ENVIRONMENT_NAME", "Turaif pilot on Render")
    monkeypatch.setenv("PIOS_FRONTEND_BASE_URL", "https://pios-frontend.onrender.com")
    monkeypatch.setenv("PIOS_RELEASE_VERSION", "1.4.0")
    monkeypatch.setenv("PIOS_TLS_ENABLED", "true")
    monkeypatch.setenv("PIOS_AUTH_MODE", "oidc")
    monkeypatch.setenv("PIOS_ALLOW_DEV_TOKENS", "false")
    monkeypatch.setenv("PIOS_OIDC_ISSUER", "https://pios-keycloak.onrender.com/realms/pios")
    monkeypatch.setenv("PIOS_OBJECT_STORAGE_BACKEND", "local")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


def env_rows():
    with SessionLocal() as db:
        return db.scalar(select(func.count(DeploymentEnvironment.id))) or 0


# ============================== the cause: services up, nothing registered

def test_a_running_service_is_not_a_registered_environment(client):
    """No amount of uptime creates the row. This is the reported symptom."""
    assert env_rows() == 0
    body = client.get(SUMMARY).json()
    assert body["reason"] == "no_environment"
    assert body["summary"]["deployment_ready"] is False


def test_the_summary_explains_what_blocks_registration(client):
    """A dead end is not an answer - the screen must name what to set."""
    body = client.get(SUMMARY).json()
    assert body["reason"] == "no_environment"
    problems = body["declaration_problems"]
    assert problems, "the screen offers no way forward"
    assert any("PIOS_DEPLOYMENT_ENVIRONMENT_TYPE" in p for p in problems)


# ============================== refusing to guess

def test_registration_is_refused_without_a_declared_type(client):
    """environment_type decides prod_like, so a default would be a verdict.

    Defaulting it to Integration would waive DEV_TOKENS_DISABLED, TLS_ENABLED,
    CORS_RESTRICTED, OBJECT_STORAGE_CONFIGURED, OIDC_MODE_ENABLED and
    MONITORING_ENABLED in one step - six security gates passed by a value
    nobody set.
    """
    get_settings.cache_clear()
    r = client.post(REGISTER)
    assert r.status_code == 422, r.text
    assert any("PIOS_DEPLOYMENT_ENVIRONMENT_TYPE" in p for p in r.json()["detail"]["problems"])
    assert env_rows() == 0, "a refused registration still created a row"


def test_a_production_like_type_rejects_the_localhost_frontend_default(client, monkeypatch):
    """FRONTEND_URL_CONFIGURED would PASS on http://localhost:8080.

    That is the dangerous direction: a gate reporting success about an address
    that is not this deployment. A default of `false` can only fail a gate and
    is safe; a default that names a place is not.
    """
    monkeypatch.setenv("PIOS_DEPLOYMENT_ENVIRONMENT_TYPE", "Production")
    monkeypatch.setenv("PIOS_DEPLOYMENT_ENVIRONMENT_CODE", "prod-01")
    monkeypatch.delenv("PIOS_FRONTEND_BASE_URL", raising=False)
    get_settings.cache_clear()
    r = client.post(REGISTER)
    assert r.status_code == 422
    assert any("PIOS_FRONTEND_BASE_URL" in p for p in r.json()["detail"]["problems"])
    assert env_rows() == 0
    monkeypatch.undo()
    get_settings.cache_clear()


def test_a_production_like_type_rejects_the_local_code_default(client, monkeypatch):
    monkeypatch.setenv("PIOS_DEPLOYMENT_ENVIRONMENT_TYPE", "Staging")
    monkeypatch.setenv("PIOS_FRONTEND_BASE_URL", "https://staging.example.sa")
    monkeypatch.delenv("PIOS_DEPLOYMENT_ENVIRONMENT_CODE", raising=False)
    get_settings.cache_clear()
    r = client.post(REGISTER)
    assert r.status_code == 422
    assert any("PIOS_DEPLOYMENT_ENVIRONMENT_CODE" in p for p in r.json()["detail"]["problems"])
    monkeypatch.undo()
    get_settings.cache_clear()


def test_an_unknown_environment_type_is_refused(client, monkeypatch):
    monkeypatch.setenv("PIOS_DEPLOYMENT_ENVIRONMENT_TYPE", "Prod")   # not a catalog value
    get_settings.cache_clear()
    r = client.post(REGISTER)
    assert r.status_code == 422
    assert any("not one of" in p for p in r.json()["detail"]["problems"])
    monkeypatch.undo()
    get_settings.cache_clear()


def test_integration_tolerates_local_defaults(client, monkeypatch):
    """The guards exist to protect production rules, not to block a laptop."""
    monkeypatch.setenv("PIOS_DEPLOYMENT_ENVIRONMENT_TYPE", "Integration")
    get_settings.cache_clear()
    body = client.get(DECLARE).json()
    assert body["problems"] == []
    assert client.post(REGISTER).status_code == 201
    monkeypatch.undo()
    get_settings.cache_clear()


# ============================== what registration actually records

def test_every_field_traces_to_a_declaration_or_a_probe(client, render_like):
    body = client.post(REGISTER).json()
    env = body["environment"]
    assert body["created"] is True
    assert env["code"] == "render-pilot"                       # PIOS_DEPLOYMENT_ENVIRONMENT_CODE
    assert env["name"] == "Turaif pilot on Render"             # ..._NAME
    assert env["environment_type"] == "Pilot"                  # ..._TYPE
    assert env["frontend_base_url"] == "https://pios-frontend.onrender.com"
    assert env["release_version"] == "1.4.0"                   # PIOS_RELEASE_VERSION
    assert env["tls_enabled"] is True                          # PIOS_TLS_ENABLED
    assert env["auth_mode"] == "OIDC"                          # PIOS_AUTH_MODE
    assert env["oidc_issuer"] == "https://pios-keycloak.onrender.com/realms/pios"
    assert env["object_storage_kind"] == "Local"               # PIOS_OBJECT_STORAGE_BACKEND
    assert env["monitoring_enabled"] is False                  # undeclared -> safe default
    assert env["database_kind"] == "sqlite"                    # live probe of this connection
    assert env["status"] == "Registered"


def test_the_declaration_preview_matches_what_gets_registered(client, render_like):
    preview = client.get(DECLARE).json()
    assert preview["problems"] == []
    assert preview["registered"] is False
    registered = client.post(REGISTER).json()["environment"]
    for key, value in preview["fields"].items():
        assert registered[key] == value, f"{key} changed between preview and registration"
    assert client.get(DECLARE).json()["registered"] is True


def test_registering_twice_updates_rather_than_duplicates(client, render_like):
    first = client.post(REGISTER).json()
    assert first["created"] is True
    second = client.post(REGISTER).json()
    assert second["created"] is False
    assert second["environment"]["id"] == first["environment"]["id"]
    assert env_rows() == 1


def test_registration_is_audited(client, render_like):
    client.post(REGISTER)
    events = client.get("/api/v1/audit-events").json()
    rows = events if isinstance(events, list) else events.get("items", [])
    assert any(e.get("action") == "deployment.environment.register_current" for e in rows), (
        "registering a production environment left no audit trail"
    )


# ============================== the whole chain, in order

def test_register_then_evaluate_produces_real_gate_results(client, render_like):
    """The path the operator actually walks: register, evaluate, read."""
    assert client.get(SUMMARY).json()["reason"] == "no_environment"

    client.post(REGISTER)
    assert client.get(SUMMARY).json()["reason"] == "no_run"

    evaluated = client.post(EVALUATE).json()
    assert evaluated["assessed"] is True
    statuses = {x["check_code"]: x for x in evaluated["checks"]}

    # Measured against the declared Pilot environment, so production rules apply.
    assert statuses["DEV_TOKENS_DISABLED"]["status"] == "Pass"
    assert statuses["DEV_TOKENS_DISABLED"]["measured_value"] == "allow_dev_tokens=False;auth_mode=oidc"
    assert statuses["TLS_ENABLED"]["status"] == "Pass"
    assert statuses["OIDC_MODE_ENABLED"]["status"] == "Pass"
    assert statuses["FRONTEND_URL_CONFIGURED"]["status"] == "Pass"

    # Render's disk is ephemeral, so PIOS_OBJECT_STORAGE_BACKEND=local is a
    # genuine finding for a production-like deployment, not a false alarm.
    assert statuses["OBJECT_STORAGE_CONFIGURED"]["status"] == "Fail"
    # Undeclared monitoring stays failed rather than being assumed present.
    assert statuses["MONITORING_ENABLED"]["status"] == "Fail"
    # Manual gates are untouched by an automated sweep.
    assert statuses["BACKUP_RESTORE_TESTED"]["status"] == "Pending"
    assert evaluated["summary"]["deployment_ready"] is False


def test_declaring_an_integration_type_would_have_waived_the_findings(client, monkeypatch):
    """Why the type may not be defaulted, demonstrated rather than asserted.

    Identical service configuration; only the declared type differs. Under
    Integration the same real problems all report Pass.
    """
    monkeypatch.setenv("PIOS_DEPLOYMENT_ENVIRONMENT_TYPE", "Integration")
    monkeypatch.setenv("PIOS_ALLOW_DEV_TOKENS", "true")
    monkeypatch.setenv("PIOS_AUTH_MODE", "dev")
    monkeypatch.setenv("PIOS_OBJECT_STORAGE_BACKEND", "local")
    get_settings.cache_clear()
    client.post(REGISTER)
    statuses = {x["check_code"]: x["status"] for x in client.post(EVALUATE).json()["checks"]}
    assert statuses["DEV_TOKENS_DISABLED"] == "Pass"
    assert statuses["OBJECT_STORAGE_CONFIGURED"] == "Pass"
    assert statuses["MONITORING_ENABLED"] == "Pass"
    monkeypatch.undo()
    get_settings.cache_clear()


def test_the_catalog_types_are_the_ones_registration_accepts(client):
    """One vocabulary, so a type valid here cannot be invalid downstream."""
    assert PROD_LIKE_TYPES == {"Pilot", "Staging", "Production"}
    assert ENVIRONMENT_TYPES == {"Integration", "Pilot", "Staging", "Production"}
