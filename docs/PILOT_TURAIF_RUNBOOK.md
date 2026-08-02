# Turaif Pilot Runbook

## Phase 0 - Environment
- Provision PostgreSQL, object storage, TLS DNS, OIDC client and secrets.
- Apply migrations through `0004_sprint4_portal`; seed 41/266/63/75 baseline.
- Validate backup and restore before user onboarding.

## Phase 1 - Identity and ownership
- Map roles: AccreditationLead, MedicationSafety, PharmacyDirector, EvidenceCollector, EvidenceReviewer, MEOwner, CAPAOwner, CAPAVerifier and ReadOnlyAuditor.
- Map every user to TGH site scope and verify least privilege.
- Assign owners for the 48 P0 collection-pack elements and all open CAPA.

## Phase 2 - Controlled campaign
- Open a 30-day pilot Evidence Campaign for P0/ESR only.
- Collect representative evidence across sites and shifts; review independently.
- Generate Findings automatically for rejected/partial/contradictory evidence.
- Close CAPA only after successful Effectiveness Check.

## Phase 3 - UAT
- Execute all scenarios in `UAT_SCENARIOS.md` with named testers.
- Record defects by severity; P0/P1 defects block go-live.
- Verify Arabic RTL, mobile layout, exports, notifications, audit and access control.

## Phase 4 - Go-live decision
- Require signed acceptance from Pharmacy Director, Medication Safety, Accreditation Lead, IT Security and Data Protection.
- No false-green rule: any P0 or ESR red keeps status `CriticalOpenActions`.
- Freeze configuration, take backup, publish support rota and rollback trigger.

## Rollback triggers
- Authentication or site-scope breach.
- Evidence file integrity failure or loss of audit trail.
- Migration failure, irreversible data corruption or unavailable restore.
- Incorrect closure of P0/ESR without effectiveness verification.
