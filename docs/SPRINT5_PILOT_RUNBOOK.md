# Sprint 5 Pilot Runbook

## 1. Runtime
- Start PostgreSQL, MinIO, API, frontend, scheduler and the optional local Keycloak profile.
- Apply migration `0005_sprint5_pilot`.
- Run baseline validation and `sprint5_pilot_smoke.py`.

## 2. Institutional identity
- Replace local Keycloak with the institutional IdP in production.
- Map `roles`, `sub`, `email`, `name` and `sites=TGH`.
- Complete access tests for all eight required role holders.

## 3. Controlled P0/ESR campaign
- Create the pilot cycle and bootstrap exactly 48 requests.
- Do not import smoke/demo evidence as Turaif evidence.
- Review evidence independently and keep all ESR failures at P0.

## 4. UAT and decision
- Execute all 12 scenarios. P0/P1 scenarios must pass.
- Complete the 16 gate attestations with evidence references.
- Go is blocked while any required gate, role, P0 request or critical UAT remains incomplete.
