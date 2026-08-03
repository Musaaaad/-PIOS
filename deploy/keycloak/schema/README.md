# Realm schema validation

`pios-realm.json` is imported by Keycloak at first boot. Keycloak deserializes it
with Jackson onto `RealmRepresentation`, and those classes are **not** annotated
`@JsonIgnoreProperties(ignoreUnknown = true)` — so a single unrecognised field
aborts the import and the container never becomes ready.

This directory holds the machinery that stops that from happening twice.

## What broke

Sprint 23 added a top-level `postLogoutRedirectUris` field to the `pios-portal`
client. No such field exists on `ClientRepresentation` in Keycloak 25.0, so
startup failed with:

```
Unrecognized field "postLogoutRedirectUris"
(class org.keycloak.representations.idm.ClientRepresentation),
not marked as ignorable (44 known properties: ...)
```

Post-logout redirects are configured through the client **attribute**
`post.logout.redirect.uris`, which `pios-realm.json` already set to `"+"`.

## Why `"+"` is sufficient

Verified against the bytecode of `OIDCAdvancedConfigWrapper` in
`org.keycloak:keycloak-services:25.0.6`: `getPostLogoutRedirectUris()` reads the
multivalued `post.logout.redirect.uris` attribute, and where an entry is `"+"`
it substitutes the client's registered `redirectUris`. That is the same list the
removed field duplicated, so removing it changes no behaviour.

## keycloak-25.0-representations.json

The property names Keycloak accepts, per representation class. It is generated,
not hand-written — `RealmSchemaDump.java` asks Jackson itself via
`UnrecognizedPropertyException.getKnownPropertyIds()`, which is the exact set the
deserializer tests an incoming realm against. A hand-maintained list would drift;
this cannot.

`backend/tests/test_keycloak_realm_import.py` validates `pios-realm.json`
against this file on every test run, so reintroducing an unsupported field fails
in CI rather than on a Render deploy.

## Regenerating (needs network + a JDK)

Only necessary when the Keycloak image tag in `deploy/keycloak/Dockerfile`
changes. `keycloak-quarkus-runtime` is not published to Maven Central, but
`keycloak-core` — which holds the representation classes and the `JsonSerialization`
mapper used by the importer — is.

```sh
V=25.0.6                      # a concrete patch release of the image tag
M=https://repo1.maven.org/maven2
mkdir -p /tmp/kcschema/lib && cd /tmp/kcschema

curl -sO $M/org/keycloak/keycloak-core/$V/keycloak-core-$V.jar
curl -sO $M/org/keycloak/keycloak-common/$V/keycloak-common-$V.jar
for a in core databind annotations; do
  curl -sO $M/com/fasterxml/jackson/core/jackson-$a/2.17.1/jackson-$a-2.17.1.jar
done
mv *.jar lib/

javac -cp "lib/*" -d classes <path-to-repo>/deploy/keycloak/schema/RealmSchemaDump.java
java -cp "classes:lib/*" RealmSchemaDump props     # emits the property sets
java -cp "classes:lib/*" RealmSchemaDump parse \
    <path-to-repo>/deploy/keycloak/pios-realm.json # exits non-zero on a bad realm
```

`parse` runs the importer's own code path — `JsonSerialization.readValue(stream,
RealmRepresentation.class)` — so a realm that parses here is one Keycloak's
importer will accept.

The image tag `25.0` floats across patch releases, so the property sets were
generated from `25.0.6` and confirmed identical on `25.0.0`, the two ends of the
range that tag can resolve to.

## Scope

This validates that the realm **file** is well-formed and that its OIDC
invariants hold. It is not a deployment test: it does not start Keycloak, reach a
database, or exercise a live sign-in.
