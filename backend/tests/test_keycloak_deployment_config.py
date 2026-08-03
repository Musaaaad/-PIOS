"""Sprint 23.2: cross-file invariants the Keycloak deployment depends on.

The realm file being importable is necessary but not sufficient. Three settings
live in three different files and must agree, and nothing before this suite
checked that they do - each mismatch is invisible in review and only shows up as
a service that never becomes healthy on Render.

  * render.yaml's healthCheckPath  <-> the Dockerfile's observability interface
  * render.yaml's KC_DB_SCHEMA     <-> the schema bootstrap_db.py actually creates
  * the Keycloak service's region  <-> the database's region

None of this starts Keycloak or contacts Render. It checks that the committed
configuration is internally consistent, nothing more.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER_YAML = REPO_ROOT / "render.yaml"
DOCKERFILE = REPO_ROOT / "deploy" / "keycloak" / "Dockerfile"
BOOTSTRAP = REPO_ROOT / "backend" / "scripts" / "bootstrap_db.py"

SERVICE_NAME = "pios-keycloak"


@pytest.fixture(scope="module")
def blueprint() -> dict:
    return yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def keycloak_service(blueprint) -> dict:
    for service in blueprint["services"]:
        if service["name"] == SERVICE_NAME:
            return service
    pytest.fail(f"{SERVICE_NAME} is missing from render.yaml")


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def env_value(service: dict, key: str) -> str | None:
    for entry in service.get("envVars", []):
        if entry.get("key") == key:
            return entry.get("value")
    return None


def docker_env(dockerfile: str, key: str) -> list[str]:
    """Every value assigned to an ENV key, in stage order."""
    return re.findall(rf"^ENV\s+{re.escape(key)}=(\S+)\s*$", dockerfile, re.MULTILINE)


# ------------------------------------------------------- health check is reachable

def test_health_endpoint_is_served_on_the_port_render_polls(keycloak_service, dockerfile):
    """Keycloak 25 moved health to a management interface on port 9000.

    Render routes only the one port the app binds, so a healthCheckPath is
    unreachable unless health is put back on the main HTTP server. Without this
    the service fails its health check however healthy Keycloak is.
    """
    if not keycloak_service.get("healthCheckPath"):
        pytest.skip("no healthCheckPath configured, so nothing to keep reachable")

    values = docker_env(dockerfile, "KC_LEGACY_OBSERVABILITY_INTERFACE")
    assert values, (
        "render.yaml health-checks "
        f"{keycloak_service['healthCheckPath']} on the main port, but the "
        "Dockerfile does not set KC_LEGACY_OBSERVABILITY_INTERFACE. On Keycloak "
        "25 that path is served on the management interface (port 9000), which "
        "Render cannot reach."
    )
    assert all(v == "true" for v in values), values


def test_observability_flag_is_set_before_the_build_and_matches_at_runtime(dockerfile):
    """It is a build-time option, so it must be set before kc.sh build."""
    # Anchor on the RUN instruction, not the first prose mention of it.
    run_build = re.search(r"^RUN\s+.*kc\.sh\s+build", dockerfile, re.MULTILINE)
    assert run_build, "no `RUN ... kc.sh build` step found in the Dockerfile"
    before = dockerfile[: run_build.start()]
    assert "KC_LEGACY_OBSERVABILITY_INTERFACE=true" in before, (
        "build-time options set only in the runtime stage are not baked into "
        "the optimized image"
    )
    values = docker_env(dockerfile, "KC_LEGACY_OBSERVABILITY_INTERFACE")
    assert len(set(values)) == 1, (
        f"the builder and runtime stages disagree: {values}"
    )


def test_health_endpoints_are_actually_enabled(keycloak_service, dockerfile):
    """The health paths do not exist at all unless health is enabled."""
    if not keycloak_service.get("healthCheckPath"):
        pytest.skip("no healthCheckPath configured")
    assert docker_env(dockerfile, "KC_HEALTH_ENABLED") == ["true", "true"], (
        "KC_HEALTH_ENABLED must be true in both stages for /health/* to exist"
    )


# --------------------------------------------------- database schema is created

def test_keycloak_db_schema_matches_the_one_bootstrap_creates():
    """Keycloak's Liquibase populates a schema but will not create it.

    backend/scripts/bootstrap_db.py creates it. If render.yaml names a different
    one, Keycloak migrates into a schema nobody made and fails on first start.
    """
    blueprint = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    service = next(s for s in blueprint["services"] if s["name"] == SERVICE_NAME)
    configured = env_value(service, "KC_DB_SCHEMA")
    assert configured, "KC_DB_SCHEMA must be set, or Keycloak lands in `public`"

    source = BOOTSTRAP.read_text(encoding="utf-8")
    default = re.search(
        r'PIOS_KEYCLOAK_SCHEMA["\']\s*,\s*["\'](\w+)["\']', source
    )
    assert default, "could not find the schema default in bootstrap_db.py"
    assert configured == default.group(1), (
        f"render.yaml asks Keycloak for schema {configured!r} but "
        f"bootstrap_db.py creates {default.group(1)!r}"
    )


def test_keycloak_stays_out_of_the_public_schema(keycloak_service):
    """`public` holds the 92 PIOS tables and the counts bootstrap_db verifies."""
    assert env_value(keycloak_service, "KC_DB_SCHEMA") != "public", (
        "Keycloak's ~95 tables in `public` would break both the emptiness check "
        "and the 92/1305/72/203/374 catalog verification"
    )


# ----------------------------------------------------------- region consistency

def test_keycloak_shares_a_region_with_the_database(blueprint, keycloak_service):
    """Render's internal connection string only resolves within one region."""
    database = blueprint["databases"][0]
    assert keycloak_service["region"] == database["region"], (
        f"{SERVICE_NAME} is in {keycloak_service['region']} but "
        f"{database['name']} is in {database['region']}; the internal "
        f"connection string will not resolve"
    )


def test_keycloak_uses_the_shared_database(keycloak_service):
    """Render's free tier allows one PostgreSQL instance per account."""
    for entry in keycloak_service.get("envVars", []):
        if entry.get("key") == "DATABASE_URL":
            assert entry["fromDatabase"]["name"] == "pios-db"
            return
    pytest.fail("pios-keycloak has no DATABASE_URL wired to pios-db")
