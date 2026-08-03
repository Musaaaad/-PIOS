"""Sprint 23.2: the pios realm must remain importable by Keycloak 25.0.

Keycloak deserializes deploy/keycloak/pios-realm.json onto RealmRepresentation
with Jackson. Those classes are not annotated @JsonIgnoreProperties(ignoreUnknown
= true), so ONE unrecognised field aborts the realm import and the container
never becomes ready - which is exactly how Sprint 23 shipped: a top-level
`postLogoutRedirectUris` on the client, a field ClientRepresentation does not
have in this version.

The allowlist these tests check against is generated from the real Keycloak
artifact, not written by hand - see deploy/keycloak/schema/README.md. Jackson is
asked directly which properties it accepts, so the allowlist cannot drift away
from the behaviour it is meant to predict.

What this suite does NOT do: start Keycloak, touch a database, or perform a live
sign-in. It proves the realm file is acceptable to the importer and that its OIDC
invariants are intact. Nothing here is evidence of a working deployment.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REALM_PATH = REPO_ROOT / "deploy" / "keycloak" / "pios-realm.json"
SCHEMA_PATH = (
    REPO_ROOT / "deploy" / "keycloak" / "schema" / "keycloak-25.0-representations.json"
)
DOCKERFILE_PATH = REPO_ROOT / "deploy" / "keycloak" / "Dockerfile"

CLIENT_ID = "pios-portal"


@pytest.fixture(scope="module")
def realm() -> dict:
    return json.loads(REALM_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def portal(realm) -> dict:
    for client in realm["clients"]:
        if client["clientId"] == CLIENT_ID:
            return client
    pytest.fail(f"{CLIENT_ID} is missing from the realm")


def unsupported(obj: dict, schema: dict, representation: str) -> list[str]:
    known = set(schema["properties"][representation])
    return sorted(k for k in obj if k not in known)


# --------------------------------------------------------- the import contract

def test_every_realm_field_is_supported(realm, schema):
    bad = unsupported(realm, schema, "RealmRepresentation")
    assert not bad, (
        f"unsupported realm-level field(s) {bad}; Keycloak aborts the whole "
        f"import on the first one it does not recognise"
    )


def test_every_client_field_is_supported(realm, schema):
    for client in realm["clients"]:
        bad = unsupported(client, schema, "ClientRepresentation")
        assert not bad, (
            f"client {client.get('clientId')!r} carries unsupported field(s) "
            f"{bad}; these abort the realm import at container start"
        )


def test_every_protocol_mapper_field_is_supported(realm, schema):
    for client in realm["clients"]:
        for mapper in client.get("protocolMappers", []):
            bad = unsupported(mapper, schema, "ProtocolMapperRepresentation")
            assert not bad, (
                f"mapper {mapper.get('name')!r} on {client.get('clientId')!r} "
                f"carries unsupported field(s) {bad}"
            )


def test_every_role_field_is_supported(realm, schema):
    roles = realm.get("roles", {})
    assert not unsupported(roles, schema, "RolesRepresentation")
    for role in roles.get("realm", []):
        bad = unsupported(role, schema, "RoleRepresentation")
        assert not bad, f"role {role.get('name')!r} carries unsupported field(s) {bad}"


def test_post_logout_redirect_uris_is_not_a_top_level_client_field(portal, schema):
    """The exact regression. Named explicitly so the failure is self-describing."""
    assert "postLogoutRedirectUris" not in portal, (
        "postLogoutRedirectUris is not a field of ClientRepresentation in "
        "Keycloak 25.0. Configure post-logout redirects through the "
        "'post.logout.redirect.uris' client attribute instead."
    )
    assert "postLogoutRedirectUris" not in schema["properties"]["ClientRepresentation"]


def test_schema_matches_the_image_tag_actually_deployed(schema):
    """A stale allowlist would validate the realm against the wrong Keycloak."""
    tag = schema["image_tag"]
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert f"FROM {tag}" in dockerfile, (
        f"deploy/keycloak/schema/ describes {tag}, which no longer matches the "
        f"image in deploy/keycloak/Dockerfile; regenerate it per that "
        f"directory's README"
    )


# ------------------------------------------------- logout behaviour is retained

def test_logout_redirects_are_configured_via_the_client_attribute(portal):
    """'+' is Keycloak's token for 'use the registered redirect URIs'.

    Verified against OIDCAdvancedConfigWrapper in keycloak-services 25.0.6:
    getPostLogoutRedirectUris() substitutes the client's redirectUris wherever an
    entry is '+'. So this yields the same list the removed top-level field
    spelled out, and dropping that field costs no logout functionality.
    """
    assert portal["attributes"]["post.logout.redirect.uris"] == "+"


# --------------------------------------- Sprint 23 invariants that must not move

def test_client_remains_public_with_pkce_s256(portal):
    assert portal["publicClient"] is True
    assert portal["attributes"]["pkce.code.challenge.method"] == "S256"


def test_client_has_no_secret(portal):
    """A public client has no secret - which is why none can leak to the browser."""
    assert "secret" not in portal
    assert portal.get("clientAuthenticatorType") in (None, "client-secret")


def test_only_authorization_code_flow_is_enabled(portal):
    assert portal["standardFlowEnabled"] is True
    assert portal["directAccessGrantsEnabled"] is False, (
        "password grant on a public client would bypass PKCE entirely"
    )
    assert portal["implicitFlowEnabled"] is False
    assert portal["serviceAccountsEnabled"] is False


def test_redirect_and_web_origins_cover_both_frontends(portal):
    redirects = " ".join(portal["redirectUris"])
    origins = portal["webOrigins"]
    for host in ("pios-frontend.onrender.com", "musaaaad.github.io", "localhost:8080"):
        assert host in redirects, f"{host} lost its redirect URI"
    assert "https://pios-frontend.onrender.com" in origins
    assert "https://musaaaad.github.io" in origins


def test_all_nine_pios_roles_are_defined(realm):
    expected = {
        "SystemAdmin", "AccreditationLead", "PharmacyDirector", "MedicationSafety",
        "EvidenceCollector", "EvidenceReviewer", "CAPAOwner", "CAPAVerifier",
        "ReadOnlyAuditor",
    }
    assert {r["name"] for r in realm["roles"]["realm"]} == expected


def test_roles_sites_and_audience_mappers_survive(portal):
    mappers = {m["name"]: m for m in portal["protocolMappers"]}
    assert mappers["roles"]["protocolMapper"] == "oidc-usermodel-realm-role-mapper"
    assert mappers["roles"]["config"]["claim.name"] == "roles"

    assert mappers["sites"]["protocolMapper"] == "oidc-hardcoded-claim-mapper"
    assert mappers["sites"]["config"]["claim.value"] == "TGH"

    audience = mappers["pios-api-audience"]
    assert audience["protocolMapper"] == "oidc-audience-mapper"
    assert audience["config"]["included.client.audience"] == "pios-api", (
        "the backend validates aud=pios-api; without this mapper every token is "
        "rejected"
    )
