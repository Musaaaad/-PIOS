# Keycloak identity provider for PIOS, pre-built with the pios realm baked in.
#
# A two-stage build so the runtime image is "optimized": kc.sh build is run at
# image build time rather than on every container start, which matters on a
# platform where a cold start already costs tens of seconds.
#
# The realm (deploy/keycloak/pios-realm.json) is imported on first boot. It
# defines the nine PIOS role codes, the public `pios-portal` client restricted
# to Authorization Code + PKCE (S256), and the mappers that emit the `roles`,
# `sites` and `aud` claims the backend validates.
#
# No secrets are baked into this image. The admin credentials and database
# password arrive as environment variables at runtime.

FROM quay.io/keycloak/keycloak:25.0 AS builder
ENV KC_DB=postgres
ENV KC_HEALTH_ENABLED=true
ENV KC_METRICS_ENABLED=false
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:25.0
COPY --from=builder /opt/keycloak/lib/quarkus/ /opt/keycloak/lib/quarkus/
COPY pios-realm.json /opt/keycloak/data/import/pios-realm.json
COPY entrypoint.sh /opt/keycloak/entrypoint.sh

ENV KC_DB=postgres
ENV KC_HEALTH_ENABLED=true
ENV KC_HTTP_ENABLED=true
# Render terminates TLS at its edge and forwards plain HTTP, so Keycloak must
# trust the forwarding headers to build correct issuer and redirect URLs.
# Without this it advertises http://<internal-host> as the issuer and every
# token fails audience/issuer validation.
ENV KC_PROXY_HEADERS=xforwarded
ENV KC_HOSTNAME_STRICT=false
# Keycloak's `cache` option defaults to `ispn`, which starts the clustered
# Infinispan stack and its JGroups discovery. This deployment is a single
# instance on a plan that cannot scale horizontally, so there is never a second
# node to find - the discovery attempts only produce repeated warnings and cost
# startup time on a 512 MB box. `local` is the supported value for a single
# node; it is a runtime option in 25.0, so it still applies under --optimized.
# Trade-off: sessions live in memory, so a restart signs users out. That is
# already true of a single-replica deployment, and the realm, users and roles
# are in PostgreSQL either way.
ENV KC_CACHE=local

USER root
RUN chmod +x /opt/keycloak/entrypoint.sh
USER 1000

ENTRYPOINT ["/opt/keycloak/entrypoint.sh"]
