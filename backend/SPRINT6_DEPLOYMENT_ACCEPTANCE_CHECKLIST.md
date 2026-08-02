# Sprint 6 Deployment Acceptance Checklist

This checklist is a control framework, not evidence that Turaif production has passed.

1. Register the target environment and immutable release version/SHA.
2. Apply Alembic migrations through `0006_sprint6_deployment_acceptance`.
3. Validate PostgreSQL, private S3/MinIO, TLS, restricted CORS and monitoring.
4. Record a real database + object-store backup/restore run with RPO/RTO evidence.
5. Validate enterprise OIDC discovery, JWKS, issuer, audience, expiry, roles and site claims.
6. Link the Turaif pilot cycle; verify 8 users, 48 P0 requests and critical UAT pass.
7. Execute the deployment acceptance run and attach evidence to every manual check.
8. Do not record Go while any required check is Pending, Blocked or Failed.
