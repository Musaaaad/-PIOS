# Sprint 21 Runtime Enablement & Infrastructure Validation Checklist

Offline phase (no Docker, PostgreSQL server, MinIO server, OIDC server, or external infrastructure):

1. Fix backend packaging so `pip install -e './backend[dev]'` (the command CI already documents) actually succeeds.
2. Install backend dependencies in an isolated environment and run the full test suite against SQLite.
3. Isolate every test-time filesystem write (evidence, exports, backups, deployment reports, baseline releases, governance exports) so running tests never mutates committed `var/` evidence.
4. Independently recompute the schema metrics (tables/columns/indexes/foreign keys/constraints) from SQLAlchemy metadata and compare against `reports/schema_metrics_v1.4.json`.
5. Independently recompute the OpenAPI surface (paths/operations/schemas) from the live `FastAPI` app object and compare against `reports/openapi_summary_v1.4.json`.
6. Re-run `python -m compileall` on `app`, `scripts`, `migrations`, `tests`.
7. Re-run the frontend syntax/static/a11y/RTL checks (`frontend/tests/js_syntax_check.sh`).
8. Regenerate the SBOM offline and confirm it is byte-identical to the shipped `reports/PIOS_SBOM_v1.4.json`.
9. Record results in a Sprint 21 Runtime Readiness Report; do not alter any delivered/checksummed v1.7 artifact in place — add new, separately dated documents instead.

Runtime phase (requires Docker, PostgreSQL, MinIO, or an authorized OIDC issuer) is explicitly **out of scope** for this checklist and is not started until separately approved. See `docs/SPRINT21_RUNTIME_ENABLEMENT_RUNBOOK.md` for what remains there.

No offline verification in this checklist substitutes for running the same suite against a live PostgreSQL 16 instance, live MinIO, or a live institutional OIDC issuer. It reduces the risk of that runtime phase; it does not replace it.
