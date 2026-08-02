# PIOS Production Governance and Privacy

Sprint 10 adds release provenance, SBOM registration, security-control evidence, retention policies, legal holds and chained audit exports.

## Hard boundaries
- A release is never approved or published automatically.
- Required release artifacts must be immutable and checksummed. Backend, frontend, SBOM and manifest artifacts require a signature reference.
- Security checks and retention policies are institutional evidence gates, not demo labels.
- Legal hold blocks purge previews. No physical deletion is performed by the preview endpoint.
- Audit exports use a deterministic SHA-256 event chain and a file checksum.

## Production evidence still required
OIDC, TLS, private storage, database backup/restore, dependency and image scanning, approved retention periods, legal basis and human release approvals must be supplied by the institution.
