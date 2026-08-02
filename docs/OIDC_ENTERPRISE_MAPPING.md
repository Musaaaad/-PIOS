# Enterprise OIDC Mapping

Required claims: `sub`, `email`, `name`, `roles`, `sites`. The `sites` claim must include `TGH` for pilot users. Roles are deny-by-default and must map to PIOS role codes.

Validation evidence must include discovery metadata, JWKS key id, issuer, audience, expiry, token algorithm, role claim, site claim, a successful request and an expected 403 negative test. Never store bearer tokens in evidence exports.
