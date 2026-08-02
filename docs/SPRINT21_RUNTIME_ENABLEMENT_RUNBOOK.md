# Sprint 21 - Runtime Enablement & Infrastructure Validation

## Scope
Sprint 21 continues from Integration Candidate v1.7 (the production baseline). It does not add
features, change APIs, or alter the data model. It closes the gap between "tests pass against
SQLite" and "the same suite has been run against real infrastructure," and it fixes the parts of
that gap that do not require Docker, PostgreSQL, MinIO, or OIDC to fix.

## Offline work completed this sprint
- Fixed `backend/pyproject.toml`: `pip install -e './backend[dev]'` — the exact command
  `.github/workflows/ci.yml` runs — failed under setuptools 79 with "Multiple top-level packages
  discovered in a flat-layout." Added `[tool.setuptools.packages.find] include = ["app*"]`.
  `alembic.ini` already resolves `migrations` by path (`script_location = migrations`), so this
  does not change how migrations are discovered or run.
- Fixed `backend/tests/conftest.py`: the test suite was writing through the app's real
  object-storage/export/backup/deployment-report/baseline-release/governance-export roots, which
  default to paths under `backend/var/`. Running the documented CI command mutated the committed
  evidence files in that directory (new UUIDs, new timestamps) as a side effect. All six roots are
  now redirected to a session temp directory before the app is imported, the same pattern already
  used for `PIOS_DATABASE_URL`.
- Ran the full 81-test suite (70 inherited + 11 v1.7) against SQLite in an isolated environment:
  81 passed, 0 failed, 0 errors, 0 skipped.
- Independently recomputed schema metrics from live SQLAlchemy metadata (not from the shipped
  report file): 92 tables, 1,305 columns, 72 indexes, 203 foreign keys, 374 constraints — an exact
  match to `reports/schema_metrics_v1.4.json` and to the "expected" baseline in
  `RELEASE_CANDIDATE_v1.7.json` and the Integration Execution Tracker.
- Independently recomputed the OpenAPI surface from the live FastAPI app object: 191 paths, 206
  operations, 178 schemas — an exact match to `reports/openapi_summary_v1.4.json`.
- Re-ran `compileall` on `app`, `scripts`, `migrations`, `tests`, and the frontend's own
  `js_syntax_check.sh` / `static_check.py`: all pass.
- Regenerated the SBOM offline (`scripts/generate_sbom.py`); output is byte-identical to the
  shipped `reports/PIOS_SBOM_v1.4.json`.

None of the above required Docker, a PostgreSQL server, a MinIO server, or an OIDC server.

## What this offline work does and does not prove
It proves the application's own code, schema definition, and OpenAPI contract are internally
consistent and reproducible, and that the CI pipeline as documented can actually run end to end.
It does **not** prove the schema behaves identically once actually created on PostgreSQL 16
(reserved words, extension availability, real constraint/index behavior under load), does not
exercise the `s3` object-storage backend (only `local` is covered by tests), and does not exercise
a real OIDC issuer (the existing OIDC tests use a locally generated RSA keypair, not an institutional
IdP). Those remain genuine runtime-only gaps.

## Remaining runtime-only work (unchanged from the v1.7 continuation point)
1. Start `integration_v1.7/docker-compose.integration.yml` on a Docker-enabled host (PostgreSQL 16 + MinIO).
2. Apply the verified schema and seed; run `integration_v1.7/sql/verify_post_import.sql`; confirm
   actual counts match the 92/1,305/72/203/374 baseline this sprint already confirmed at the code level.
3. Re-run the 81-test suite with `PIOS_DATABASE_URL` pointed at the live PostgreSQL instance.
4. Run the S3-01 lifecycle/hash/private-access tests against MinIO.
5. Obtain an authorized institutional OIDC issuer/tenant/JWKS/test identities and run live
   positive/negative/role/revocation/site-isolation tests; wire the frontend OIDC login/logout flow.
6. Deploy the authored Kubernetes manifests, Keycloak realm, and Prometheus/Grafana configuration
   to real infrastructure.
7. Complete the frontend production-cutover checklist (`frontend/RUNTIME_CHECKLIST.md`) against a
   live backend, including real UAT with named Turaif roles.
8. Populate the Institutional Go-Live Evidence Index with real evidence and obtain the required signatures.

None of this is started by Sprint 21. It is explicitly deferred pending separate approval.

## Guardrail
This sprint makes no institutional, production, or CBAHI-compliance claim. It only establishes
that the offline-verifiable portion of the v1.7 baseline is internally consistent and that CI can
run without silently corrupting shipped evidence.
