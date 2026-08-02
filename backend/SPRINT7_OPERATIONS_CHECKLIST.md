# Sprint 7 Operations, Cutover and Baseline Checklist

This checklist is a controlled pre-go-live rehearsal. It is not evidence that Turaif has gone live.

## Production operations
- Bootstrap the six default SLOs for TGH.
- Connect monitoring sources and record measurements with evidence references.
- Confirm each breach creates or links an operational incident.
- Configure P0/P1 escalation, support rota and rollback authority.

## Cutover
- Create a cutover run linked to the accepted deployment environment.
- Complete all 20 cutover tasks and attach evidence.
- Confirm the latest deployment acceptance outcome is Pass.
- Confirm no open P0/P1 operational incident exists.
- Record the formal Go, NoGo or Rollback decision.

## Baseline release
- Calculate a 266-item readiness snapshot.
- Create an OperationalBaseline even when gaps exist; do not label it EvidenceReady.
- Approve and publish the immutable JSON package with SHA-256.
- Use EvidenceReady classification only when all critical actions are closed and ESR groups are green.
