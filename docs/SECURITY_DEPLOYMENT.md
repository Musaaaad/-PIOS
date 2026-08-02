# Security and Deployment Notes

- Production authentication uses OIDC JWT verification with issuer, audience, JWKS, role claim and site claim.
- Development tokens are rejected when `PIOS_ENV=production` or `PIOS_ALLOW_DEV_TOKENS=false`.
- Keep refresh tokens outside browser localStorage; use an approved OIDC client and secure session design.
- Restrict CORS to the portal origin and terminate TLS at the approved ingress.
- Put database, MinIO and export volumes on encrypted storage with backup and retention policies.
- Add enterprise malware scanning before accepting uploaded evidence.
- Send API and ingress logs to the central SIEM; preserve Trace ID and AuditEvent linkage.
- Review all Kubernetes secret placeholders before deployment; never commit real secrets.
