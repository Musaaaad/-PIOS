# Deployment Acceptance — where every gate comes from

The "قبول النشر المؤسسي" screen shows 24 gates. This document records, for each
one, what decides its value. It exists because the screen previously showed gate
verdicts that came from a hand-written constant in `frontend/demo-data.js` and
that no configuration change could ever move.

## The contract

| | |
|---|---|
| **Catalog** | `backend/app/services/deployment_acceptance.py` → `ACCEPTANCE_CATALOG` (24 entries) |
| **Storage** | `deployment_acceptance_runs` + `deployment_acceptance_checks` |
| **Read** | `GET /api/v1/deployment/acceptance-summary` — any authenticated principal |
| **Measure** | `POST /api/v1/deployment/acceptance-summary/evaluate` — `SystemAdmin` or `AccreditationLead` |
| **Screen** | `frontend/app.js` → `deployment()`, sourced only from the read endpoint |

Reading and measuring are deliberately different verbs, and the screen offers
them as two different buttons:

- **إعادة قراءة النتيجة المخزّنة** (`GET`) reports the latest stored run
  unchanged. It never re-derives a verdict, so a stored `Fail` stays `Fail`
  even if the service it is running in is now configured differently.
- **إعادة تقييم الفحوص الآلية** (`POST .../evaluate`) measures the automated
  gates against the process's current settings and the environment row, stores
  a new run, and writes a signed report. This is the only path that can change
  a gate's value.

## Registering the deployment

A running service is not a registered environment. "pios-api is up" is an
observation about a process; a `DeploymentEnvironment` row is a record someone
creates. No seed, migration or startup hook has ever created one — which is why
the screen reports `no_environment` on a perfectly healthy Render stack.

`POST /deployment/environments/register-current` (SystemAdmin, AccreditationLead
or PharmacyDirector — the same roles that could always create one by hand)
records the deployment the process is running in. Preview it first with
`GET /deployment/environments/current/declaration`.

Nothing is inferred. Each field is either a value the operator declared through
the service's own environment or a live probe of its database:

| Field | Source |
|---|---|
| `code` / `name` | `PIOS_DEPLOYMENT_ENVIRONMENT_CODE` / `_NAME` |
| `environment_type` | `PIOS_DEPLOYMENT_ENVIRONMENT_TYPE` — **required, no default** |
| `frontend_base_url` | `PIOS_FRONTEND_BASE_URL` |
| `release_version` / `release_sha` | `PIOS_RELEASE_VERSION` / `PIOS_RELEASE_SHA` |
| `auth_mode` | `PIOS_AUTH_MODE` |
| `oidc_issuer` | `PIOS_OIDC_ISSUER` |
| `object_storage_kind` | `PIOS_OBJECT_STORAGE_BACKEND` |
| `tls_enabled` | `PIOS_TLS_ENABLED` |
| `monitoring_enabled` | `PIOS_MONITORING_ENABLED` |
| `database_kind` / `database_version` | live probe of the bound connection |

Registration is **refused** (422, listing the exact variables) when a
declaration is absent or still at a local-development default that a gate would
wrongly pass on. The distinction the guards enforce:

- A default of `false` — monitoring, TLS — is safe. It can only make a gate
  *fail*, and a gate that fails for want of a declaration is telling the truth.
- A default that *names a place* — `local`, `http://localhost:8080` — is not.
  `FRONTEND_URL_CONFIGURED` would report Pass about a machine that is not this
  deployment.
- `environment_type` may never be defaulted at all. It decides `prod_like`, and
  a default of `Integration` would waive `DEV_TOKENS_DISABLED`, `TLS_ENABLED`,
  `CORS_RESTRICTED`, `OBJECT_STORAGE_CONFIGURED`, `OIDC_MODE_ENABLED` and
  `MONITORING_ENABLED` in one step — six security gates passed by a value
  nobody set.

## Fail-closed rules

1. No `DeploymentEnvironment` registered → `assessed: false`,
   `reason: "no_environment"`, all 24 gates `NotAssessed`,
   `deployment_ready: false`. `POST .../evaluate` answers **409** and creates
   nothing — auto-registering an environment would fabricate the very inputs
   the gates measure (`environment_type` decides `prod_like`, `tls_enabled`
   decides `TLS_ENABLED`, `object_storage_kind` decides
   `OBJECT_STORAGE_CONFIGURED`).
2. Environment registered, no run → `reason: "no_run"`, same fail-closed
   rollup.
3. A run with zero check rows → `reason: "run_has_no_checks"`. Its empty
   rollup would otherwise score zero required blockers and read as `Pass`.
4. `NotAssessed` is not a stored `CheckStatus`. An unmeasured gate can never
   collide with a measured one in either direction.
5. `Pending` is never `Pass`. Missing evidence is never `Pass`. There is no
   demo, mock or default-to-pass branch on any of these paths.

## Gate sources

`Automated` gates are measured by `execute_automated_checks()` on each
evaluation. `Manual` gates stay `Pending` until a human records evidence via
`PATCH /deployment/acceptance-runs/{run_id}/checks/{check_code}` — an automated
sweep supplies none of them, which is the correct answer, not a defect.

`prod_like` below means `environment_type ∈ {Pilot, Staging, Production}`. Gates
guarded by it pass automatically in an `Integration` environment.

| Gate | Category | Mode | Decided by |
|---|---|---|---|
| `API_HEALTH` | Platform | Automated | `settings.release_version`, `settings.env` |
| `DATABASE_REACHABLE` | Database | Automated | `SELECT 1` against the bound engine |
| `SCHEMA_TABLES_PRESENT` | Database | Automated | Reflected table count vs `Base.metadata.tables` |
| `BASELINE_COUNTS_VALID` | Data | Automated | Row counts must equal 41/266/63/75/12 |
| `MIGRATIONS_APPLIED` | Database | **Manual** | Operator confirms Alembic head in the target database |
| `OBJECT_STORAGE_CONFIGURED` | Storage | Automated | `env.object_storage_kind` ∉ {local, filesystem} when `prod_like` |
| `OBJECT_STORAGE_PRIVATE_RW` | Storage | **Manual** | Recorded private-bucket write/read/delete test |
| `BACKUP_RESTORE_TESTED` | Resilience | **Manual** | A recorded `BackupRestoreRun` (`POST …/backup-restore-runs`) |
| `OIDC_MODE_ENABLED` | Identity | Automated | `env.auth_mode == "OIDC"` and `env.oidc_issuer` set, when `prod_like` |
| `OIDC_DISCOVERY_JWKS` | Identity | **Manual** | A recorded `OidcValidationRun` |
| `OIDC_TOKEN_VALIDATION` | Identity | **Manual** | A recorded `OidcValidationRun` (`POST …/oidc-validations`) |
| `OIDC_ROLE_SITE_CLAIMS` | Identity | **Manual** | Operator confirms least-privilege role/site claim mapping |
| `DEV_TOKENS_DISABLED` | Security | Automated | `not settings.allow_dev_tokens and settings.auth_mode == "oidc"`, when `prod_like`. Records `allow_dev_tokens=<bool>;auth_mode=<mode>` |
| `TLS_ENABLED` | Security | Automated | `env.tls_enabled`, when `prod_like` |
| `CORS_RESTRICTED` | Security | Automated | `settings.cors_origin_list`: non-empty, no `*`, no localhost/127.0.0.1 when `prod_like` |
| `MONITORING_ENABLED` | Operations | Automated | `env.monitoring_enabled`, when `prod_like` |
| `AUDIT_WRITE_PASS` | Audit | Automated | `audit_events` table present |
| `FRONTEND_URL_CONFIGURED` | Frontend | Automated | `env.frontend_base_url` set |
| `NOTIFICATION_SCHEDULER_PASS` | Operations | **Manual** | Operator records a duplicate-free scheduler run |
| `EXPORT_RETENTION_PASS` | Operations | **Manual** | Operator records export generation, checksum and cleanup |
| `PILOT_USERS_READY` | Pilot | Automated | Linked pilot: ≥8 active participants covering all 8 required roles, trained and access-tested |
| `P0_CAMPAIGN_READY` | Pilot | Automated | Linked pilot's evidence campaign holds exactly 48 requests |
| `UAT_CRITICAL_PASS` | Pilot | Automated | Linked pilot's `PilotGateCheck("UAT_CRITICAL_PASS").status == "Pass"` |
| `FORMAL_GO_DECISION` | Governance | **Manual** | A recorded authorised Go/ConditionalGo decision |

The three pilot gates report `Blocked` with `"No pilot linked"` when the run
carries no `pilot_cycle_id`. `Blocked` means *cannot be measured*, and like
`Pending` it counts against `deployment_ready`.

## Not covered here

`SECURITY_ACCEPTANCE` is **not** a deployment acceptance gate. It belongs to the
pilot gate catalog in `backend/app/services/pilot_control.py` and appears on the
Pilot Center screen, which still renders `window.PIOS_DEMO.pilot`. Ten other
institutional screens (Operations, Assurance, Intelligence, Governance,
Committee, Institutional Pilot, Evidence, Findings, Documents, Intelligence to
Action) likewise still read demo constants despite having real backend
services. That is a known, recorded gap — not an accepted one.
