# Sprint 6 Deployment Acceptance Runbook

## Purpose
Provide evidence-based acceptance for the Turaif pilot environment. A local smoke result is not an institutional Go decision.

## Order of execution
1. Register the immutable environment release and target URLs.
2. Apply Alembic through `0006_sprint6_deployment_acceptance`.
3. Execute automated acceptance checks.
4. Perform real PostgreSQL and object-storage backup/restore and record RPO/RTO.
5. Validate enterprise OIDC discovery, JWKS, token signature, issuer, audience, expiry, roles and sites.
6. Link the approved pilot cycle and verify 8 users, 48 P0 requests and critical UAT.
7. Attach evidence to every manual check.
8. Record Go only when all required checks are Pass or formally Waived.

## Non-negotiable blockers
- Development tokens in Pilot/Staging/Production.
- Local filesystem evidence storage in production-like environments.
- Missing backup/restore evidence.
- Missing OIDC role/site claim validation.
- Any failed P0/P1 UAT or required deployment check.
