# Sprint 4 Runtime Acceptance

1. Set `PIOS_AUTH_MODE=oidc`, issuer, audience and JWKS URL; disable development tokens in production.
2. Run Alembic through `0004_sprint4_portal` and verify `notifications` and `export_jobs`.
3. Calculate a readiness snapshot and confirm Dashboard, Standards and Worklist endpoints.
4. Create overdue Evidence/Finding/CAPA records, run notification refresh and verify idempotency.
5. Generate readiness CSV and Executive ZIP; verify SHA-256, download authorization and retention.
6. Serve the frontend over TLS and restrict CORS to the approved portal origin.
7. Map IdP groups to PIOS roles and sites; test least privilege for Collector, Owner, Verifier and Auditor.
8. Configure the scheduled notification refresh and export cleanup jobs.
9. Verify audit events contain Trace IDs for notification state changes and exports.
10. Complete pilot UAT with Turaif users and record defects, training attendance and go-live decision.
