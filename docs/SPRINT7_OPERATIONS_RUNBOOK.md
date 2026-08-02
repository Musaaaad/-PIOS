# Sprint 7 Production Operations Runbook

## Purpose
Operate PIOS safely after deployment acceptance, control the cutover, record incidents, monitor service levels, and publish a truthful first readiness baseline.

## Service-level objectives
The default catalog includes API availability, p95 latency, evidence upload success, notification job success, export integrity, and backup freshness. Measurements are immutable per objective and time window. A breach creates a linked operational incident.

## Incident lifecycle
Open -> Acknowledged -> Mitigated -> Resolved -> Closed. A closed incident requires both root cause and resolution summary. Reopened incidents immediately block a green cutover when severity is P0 or P1.

## Cutover governance
The command center creates 20 tasks across PreGo, Freeze, Deploy, Validate, Activate, Observe and Close. Go is blocked unless:
- all critical cutover tasks pass;
- latest deployment acceptance outcome is Pass;
- no open P0/P1 operational incident exists;
- linked pilot decision, when present, is Go or ConditionalGo.

## Baseline publication
OperationalBaseline records the actual state, including gaps and critical actions. EvidenceReady is a stronger claim and is blocked unless the snapshot is EvidenceReady, has no critical open actions, and all ESR groups are green.

## Rollback triggers
Trigger rollback for patient-safety risk, loss of evidence integrity, OIDC scope failure, unsuccessful restore, sustained P0 SLO breach, or any formal NoGo/Rollback decision.
