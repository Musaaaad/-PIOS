# Deployment Pipeline

Sprint 22 adds two independent, automated deployment paths from `main`. They
are deliberately separate because they have very different prerequisites.

| Path | Deploys | External account needed | Secrets needed | Produces a public HTTPS URL |
|---|---|---|---|---|
| **A. GitHub Pages** | frontend only | none | none | yes, automatically |
| **B. Render** | full stack (API + PostgreSQL + frontend) | yes | yes | yes, once configured |

Path A works the moment this is merged. Path B cannot work until someone with a
hosting account completes the one-time setup in section B — no automation can
create that account or those credentials on your behalf.

---

## A. GitHub Pages — frontend, no setup required

**Workflow:** `.github/workflows/deploy-pages.yml`
**Trigger:** push to `main` touching `frontend/**`, or manual `workflow_dispatch`
**Result URL:** `https://<owner>.github.io/<repo>/` — for this repository,
`https://musaaaad.github.io/-PIOS/`

What it does:

1. Runs the frontend's own syntax/static/a11y/RTL checks. A broken bundle never
   reaches a public URL.
2. Stages `frontend/` into `_site/`, dropping `tests/`, `Dockerfile`,
   `nginx.conf` and `MANIFEST.txt` (build inputs, not site content).
3. Generates `_site/config.js` at build time. The committed
   `frontend/config.js` is never modified. **`defaultToken` is emptied** —
   the committed default is a development token
   (`dev:portal-user:AccreditationLead,...`) and must not be published to a
   public URL.
4. Injects the `Content-Security-Policy` from `nginx.conf` as a `<meta>` tag,
   since Pages cannot serve custom response headers.
5. Enables Pages automatically (`actions/configure-pages` with
   `enablement: true`), so no manual repository setting change is needed.
6. Deploys, then runs `deploy/verify_deployment.py` against the live URL and
   fails the run if the deployed site does not answer correctly.
7. Writes the live URL to the workflow summary.

### Demo mode — read this before sharing the link

Pages serves static files only. It cannot run FastAPI or PostgreSQL. With no
API configured the app falls back to its built-in demo mode and displays
**clearly labelled synthetic data** (the Arabic banner reads
"بيانات عرض تجريبية غير معتمدة" — unapproved demonstration data).

This is a genuine, working, mobile-Safari-compatible URL for the interface. It
is **not** a live system and must not be presented as institutional data.

To point the Pages build at a real API, set a repository **variable** (not a
secret — it is a public URL):

- Settings → Secrets and variables → Actions → **Variables** → New variable
- Name: `PIOS_API_BASE_URL`
- Value: e.g. `https://pios-api.onrender.com/api/v1`

The API must send CORS headers permitting the Pages origin, or the browser
will block the calls and the app will fall back to demo mode.

---

## B. Render — full stack

**Workflow:** `.github/workflows/deploy-production.yml`
**Blueprint:** `render.yaml`
**Trigger:** push to `main`, or manual `workflow_dispatch`

If the required secrets are absent this workflow **reports and stops without
failing**, so an unconfigured repository keeps a green pipeline instead of a
permanently red one. It does not silently pretend to deploy.

### Topology

The frontend is already live on GitHub Pages, so the intended shape is:

    https://musaaaad.github.io/-PIOS/   (Pages, already deployed)
                  |
                  |  HTTPS, cross-origin -> requires PIOS_CORS_ORIGINS
                  v
    https://pios-api.onrender.com       (Render: FastAPI + PostgreSQL 16)

`render.yaml` also defines an optional `pios-frontend` static site as a
same-origin alternative. Delete that service from the blueprint if you only
want the Pages frontend.

### One-time setup

1. **Create a Render account** at <https://render.com> (free tier is enough to
   evaluate; see the caveat below).
2. **Apply the blueprint.** Render dashboard → New → Blueprint → connect this
   repository → select `render.yaml`. This creates `pios-db` (PostgreSQL 16),
   `pios-api` and `pios-frontend`.
3. **Set the values `render.yaml` deliberately leaves blank** (marked
   `sync: false`, so they never live in the repository):

   | Service | Key | Value |
   |---|---|---|
   | pios-api | `PIOS_CORS_ORIGINS` | `https://musaaaad.github.io` — origin only: no path, no trailing slash |
   | pios-api | `PIOS_OIDC_ISSUER` | your identity provider's issuer URL |
   | pios-api | `PIOS_OIDC_AUDIENCE` | e.g. `pios-api` |
   | pios-api | `PIOS_OIDC_JWKS_URL` | your provider's JWKS endpoint |
   | pios-frontend | `PIOS_API_BASE_URL` | e.g. `https://pios-api.onrender.com/api/v1` (only if using the optional Render frontend) |

   `PIOS_CORS_ORIGINS` must be the bare origin. `app/main.py` passes it
   straight to Starlette's `CORSMiddleware`, which matches the browser's
   `Origin` header exactly — `https://musaaaad.github.io/-PIOS/` would never
   match and every API call would be blocked, silently dropping the app back
   into demo mode.

   Until the OIDC values are set the API rejects all authentication. That is
   the correct failure mode for a production deployment — it is not broken.

4. **Point the Pages frontend at the live API.** Repository → Settings →
   Secrets and variables → Actions → **Variables** → New repository variable:

   - Name: `PIOS_API_BASE_URL`
   - Value: `https://pios-api.onrender.com/api/v1`

   Then re-run the **Deploy Frontend (GitHub Pages)** workflow. The build
   switches `demoMode` to `false` and the app begins calling the live backend.

### Region

`pios-db` and `pios-api` are both pinned to `frankfurt`. They **must** stay in
the same region: Render's internal connection string only resolves within a
region, and omitting the key on the database silently defaults it to Oregon,
which leaves the API unable to reach it.

4. **Add the GitHub repository secrets** (Settings → Secrets and variables →
   Actions → **Secrets**):

   | Secret | Where to get it | Required |
   |---|---|---|
   | `RENDER_API_KEY` | Render → Account Settings → API Keys → Create API Key | yes |
   | `RENDER_API_SERVICE_ID` | the `pios-api` service URL, the `srv-...` segment | yes |

   These are the only secrets this pipeline needs. Do not commit them, and do
   not paste them into `render.yaml`.

### What the deploy workflow does

1. **Preflight** — checks the secrets exist; reports precisely which are
   missing and stops cleanly if not.
2. **Resolve** the live service URL from the Render API.
3. **Trigger** a deploy and record the deploy id.
4. **Poll** until the deploy reports `live`, failing fast on
   `build_failed` / `update_failed` / `canceled`, with a 25-minute ceiling.
5. **Verify** with `deploy/verify_deployment.py` and fail the run if the live
   service misbehaves.
6. **Publish** the URL to the workflow summary and upload the JSON report.

### Free-plan caveats

Render free web services sleep after inactivity and cold-start on the next
request (tens of seconds), and free PostgreSQL instances **expire after 30
days**. Fine for a demonstration; move to a paid plan for anything else.

---

## Database provisioning on first boot

`backend/scripts/render_entrypoint.sh` runs before the API server starts and:

1. Accepts the platform's injected `DATABASE_URL` when `PIOS_DATABASE_URL` is
   unset.
2. Normalises the scheme to `postgresql+psycopg://`. Managed Postgres add-ons
   inject `postgres://` or `postgresql://`; SQLAlchemy maps a bare
   `postgresql://` to psycopg2, which this backend does not install. Without
   this the app fails at import.
3. Runs `backend/scripts/bootstrap_db.py`.

`bootstrap_db.py` is the container-safe counterpart to
`fresh_install_postgresql.sh` (which needs `psql`, absent from the image):

- **Empty database** → applies the verified schema and seed, verifies the five
  catalog metrics (92 tables / 1,305 columns / 72 indexes / 203 foreign keys /
  374 constraints), then `alembic stamp head`.
- **Already provisioned** → verifies the metrics and exits, writing nothing.
  Safe on every redeploy.
- **Verification failure** → exits non-zero, so the container fails to start
  rather than serving a half-built database.

It never runs `alembic upgrade head`, per `docs/DATABASE_MIGRATION_POLICY.md`:
that command cannot complete against an empty database, because revision `0011`
collides with objects revision `0001` already creates.

Metric counting excludes Alembic's own `alembic_version` table. Counting it
would make the first boot pass (verified before stamping) and then fail every
redeploy (verified after stamping) — this was found and fixed by testing the
redeploy path against a real PostgreSQL 16 server, not by inspection.

Set `PIOS_SKIP_DB_BOOTSTRAP=true` to skip provisioning entirely, e.g. when the
database is managed by a separate migration job.

---

## Post-deploy verification

`deploy/verify_deployment.py` is used by both workflows and is runnable by hand:

    python deploy/verify_deployment.py \
      --api-url https://pios-api.onrender.com \
      --frontend-url https://musaaaad.github.io/-PIOS/ \
      --expect-version 1.4.0 \
      --report verification.json

| Check | Passes when |
|---|---|
| `api.reachable` | `/health` answers within the timeout |
| `api.health` | HTTP 200 and `status == "ok"` |
| `api.version` | reported version matches `--expect-version` |
| `api.ready.database` | `/ready` reports `database == "reachable"` |
| `api.openapi` | `/openapi.json` served with a non-empty path set |
| `api.auth_required` | `/api/v1/identity/me` returns **401/403** to an anonymous caller |
| `frontend.http` | page returns HTTP 200 |
| `frontend.app_shell` | `id="app"`, `id="main"`, `dir="rtl"` all present |
| `frontend.asset.*` | `config.js`, `app.js`, `styles.css` all resolve |

`api.auth_required` is a deliberate security gate: a deployment that returns
200 there is serving protected data to anonymous callers, and the deploy is
failed. This was confirmed to work by pointing the verifier at a deliberately
misconfigured instance running with development tokens enabled — it correctly
failed.

Only public, unauthenticated endpoints are exercised. No credentials are sent
or logged.

---

## What is NOT claimed

- No institutional, production, CBAHI compliance, or Go-Live readiness claim.
- The Pages URL serves the interface in demo mode with synthetic data.
- Object storage (MinIO/S3) and institutional OIDC remain unvalidated at
  runtime; see `SPRINT21_RUNTIME_VALIDATION/blocker_register.json`.
- Neither workflow has been executed against a live hosting account from this
  environment. They are verified by local execution of every step that can run
  locally: YAML validity, the frontend build, config generation, CSP injection,
  the database bootstrap against a real PostgreSQL 16 server (first boot,
  redeploy, and platform-style `postgres://` URL), and the verification script
  against a real running backend and frontend, including its failure modes.
