# Institutional Authentication (OIDC) — Setup

Sprint 23 replaces the development-token placeholder with real institutional
authentication: OpenID Connect **Authorization Code flow with PKCE**, served by
Keycloak, with roles and site scope carried in the access token.

No development token, no shared password, and no temporary bypass exists in this
path. `app/core/security.py` refuses development tokens whenever
`PIOS_ENV=production`, and a test asserts that.

## Why this design

| Decision | Reason |
|---|---|
| **Keycloak, self-hosted on Render** | `deploy/keycloak/pios-realm.json` already existed and defines the nine PIOS role codes. No external identity account, no per-seat cost, and the realm is version-controlled with the code it protects. |
| **Public client + PKCE, not a confidential client** | A browser cannot keep a secret. PKCE proves possession of the `code_verifier` instead, so **no client secret exists to leak**. The build fails outright if anything secret-shaped reaches the bundle. |
| **`sessionStorage`, not `localStorage`** | Scoped to the tab and cleared when it closes. `frontend/RUNTIME_CHECKLIST.md` item 4 requires refresh tokens stay out of `localStorage`. |
| **Authorization Code only** | `directAccessGrantsEnabled` and `implicitFlowEnabled` are both **false** in the realm. Password grant on a public client would bypass PKCE entirely. |

### Residual risk, stated plainly

A refresh token in `sessionStorage` is readable by script running in that tab, so
a cross-site-scripting flaw could exfiltrate it. The stronger design is a
backend-for-frontend holding tokens in an `HttpOnly` cookie. That is a larger
change than this sprint, and the mitigations in place — a strict CSP, short
access-token lifetimes, and no secret in the bundle — reduce but do **not**
eliminate this. It should be revisited before any real patient-adjacent data
enters the system.

## What the realm provides

`deploy/keycloak/pios-realm.json`:

- **Nine realm roles**: `SystemAdmin`, `AccreditationLead`, `PharmacyDirector`,
  `MedicationSafety`, `EvidenceCollector`, `EvidenceReviewer`, `CAPAOwner`,
  `CAPAVerifier`, `ReadOnlyAuditor` — the exact codes `require_roles(...)` checks.
- **Client `pios-portal`**: public, PKCE S256, Authorization Code only.
- **Three mappers**:
  - `roles` → realm roles into the `roles` claim (`PIOS_OIDC_ROLES_CLAIM`)
  - `sites` → hardcoded `TGH` into the `sites` claim (`PIOS_OIDC_SITE_CLAIM`)
  - `pios-api-audience` → adds `pios-api` to `aud`, which the backend validates

Redirect URIs cover the Render frontend, the GitHub Pages frontend, and
`localhost:8080` for development.

## Configuration values

These are **derived from the realm and service names**, not invented:

| Variable | Service | Value |
|---|---|---|
| `PIOS_OIDC_ISSUER` | pios-api **and** pios-frontend | `https://<keycloak-url>/realms/pios` |
| `PIOS_OIDC_AUDIENCE` | pios-api | `pios-api` (already set in `render.yaml`) |
| `PIOS_OIDC_JWKS_URL` | pios-api | `https://<keycloak-url>/realms/pios/protocol/openid-connect/certs` |
| `PIOS_OIDC_CLIENT_ID` | pios-frontend | `pios-portal` (already set in `render.yaml`) |

`<keycloak-url>` is the only value that cannot be known until Render assigns it.

## Sign-in flow

1. An unauthenticated visitor to a live deployment sees the Arabic login screen.
   The app does **not** show demo data dressed up as real.
2. "الدخول عبر الهوية المؤسسية" generates a `code_verifier`, derives an S256
   challenge, stores state + verifier in `sessionStorage`, and redirects.
3. Keycloak authenticates and returns `?code=...&state=...`.
4. The app rejects a mismatched `state` (CSRF defence), exchanges the code with
   the verifier, and strips `code`/`state` from the address bar.
5. Every API call sends `Authorization: Bearer <access_token>`. On a `401` the
   app attempts one silent refresh before surfacing the error.
6. "تسجيل الخروج" clears local tokens **and** ends the Keycloak session with
   `id_token_hint`.

## Free-plan reality

Keycloak on Render's free tier (512 MB, sleeps when idle) will cold-start
slowly — expect tens of seconds on the first sign-in after inactivity. Free
PostgreSQL instances also expire after 30 days. **For a real institutional
pilot, move `pios-keycloak` and both databases to a paid plan.** This is a
capacity statement, not a compliance one.

## What is NOT claimed

This document describes a working authentication mechanism verified locally
against a real RS256 token and a real JWKS. It is **not** a claim of production
readiness, CBAHI compliance, accreditation readiness, or Go-Live. Those require
the live deployment to be exercised and independently accepted.
