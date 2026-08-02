# Frontend Runtime Acceptance
1. Replace demo mode with live API and remove the default development token.
2. Confirm Arabic RTL and English LTR on desktop, tablet and mobile.
3. Verify keyboard navigation, focus states, labels and contrast.
4. Connect OIDC login/logout and token renewal; do not store production refresh tokens in localStorage.
5. Validate role-based navigation and site scope against Backend `/identity/me`.
6. Test loading, empty, error and unauthorized states for every screen.
7. Generate and download all export types with audit events.
8. Run UAT with Turaif collectors, reviewers, owners, verifiers and auditors.
