# Frontend Runtime Acceptance
1. Replace demo mode with live API and remove the default development token.
2. Confirm Arabic RTL and English LTR on desktop, tablet and mobile.
3. Verify keyboard navigation, focus states, labels and contrast.
4. Connect OIDC login/logout and token renewal; do not store production refresh tokens in localStorage.
5. Validate role-based navigation and site scope against Backend `/identity/me`.
6. Test loading, empty, error and unauthorized states for every screen.
7. Generate and download all export types with audit events.
8. Run UAT with Turaif collectors, reviewers, owners, verifiers and auditors.

## Sprint 21 status
All 8 items above still require a live backend and are unstarted. `tests/js_syntax_check.sh` and
`tests/static_check.py` were re-confirmed passing offline (route/a11y/RTL markup checks only —
not a substitute for items 2-3 above, which need a real browser/device pass). See
`docs/SPRINT21_RUNTIME_ENABLEMENT_RUNBOOK.md`.
