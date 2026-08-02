# Sprint 8 Continuous Assurance, Data Quality and Cluster Rollout Checklist

## Continuous assurance
- Bootstrap one active TGH P0/ESR program with exactly 48 controls.
- Generate recurring cycles idempotently and create one task per active control.
- Require evidence reference or a reviewer comment for Pass/Fail.
- Create a P0 Finding when a critical recurring control fails.
- Prevent cycle closure while tasks remain incomplete.

## Data quality
- Bootstrap the five data-quality rules.
- Scan missing P0 controls, overdue controls, overdue Findings, overdue CAPA and overdue document reviews.
- Preserve data-quality issues as a separate signal from clinical/accreditation Findings.

## Cluster rollout
- Create rollout waves from the Turaif template site.
- Track baseline import, users, training, deployment and OIDC gates per site.
- Do not mark a site ready until all five gates pass.

## Institutional acceptance
- Run on PostgreSQL and private object storage.
- Validate scheduler execution and notification idempotency.
- Review all automatically created P0 Findings.
- Approve each rollout wave through the cluster governance process.
