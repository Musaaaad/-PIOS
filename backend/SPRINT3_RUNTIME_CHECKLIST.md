# Sprint 3 Runtime Acceptance Checklist

1. Apply Alembic through `0003_sprint3_capa_readiness` on PostgreSQL 16+.
2. Confirm 29 tables including `readiness_snapshot_items`.
3. Execute a P0 Finding → CAPA → actions → effectiveness → closure workflow.
4. Verify no CAPA can close without completed actions and an effective verification check.
5. Verify an ineffective check reopens both CAPA and Finding.
6. Calculate a readiness snapshot and confirm exactly 266 snapshot items.
7. Confirm N/A decisions require an approved rationale and cannot bypass active findings.
8. Confirm ESR status remains Red/Amber until every ESR ME is evidence-sufficient and has no open critical finding.
9. Confirm the UI labels the score as evidence readiness, not CBAHI compliance.
10. Confirm audit events carry trace IDs for each lifecycle transition.
