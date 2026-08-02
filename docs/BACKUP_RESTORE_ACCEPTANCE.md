# Backup and Restore Acceptance

The acceptance test covers PostgreSQL plus evidence objects. Capture backup URI, SHA-256, start/end time, isolated restore target, table/object counts, link integrity, audit continuity, measured RPO/RTO and an authorized sign-off. A backup without a successful isolated restore does not pass.
