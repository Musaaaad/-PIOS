# Intelligence-to-Action Governance

## Mandatory sequence
1. Generate a deterministic risk recommendation.
2. Complete human recommendation review.
3. Record a review-board decision.
4. Create a human-owned action plan only after `AdoptForPlanning`.
5. Add owned and dated tasks.
6. Submit and independently approve the plan.
7. Execute tasks and record evidence references.
8. Request Finding or CAPA conversion separately when required.
9. Approve and execute each conversion through an authorized human endpoint.
10. Record independent completion verification before completing the plan.

## Non-delegable decisions
PIOS does not automatically approve compliance or N/A, sign evidence, create or close critical CAPA, alter KPI definitions, publish EvidenceReady, or close linked Findings/CAPA.

## Traceability
Every session, item, decision, plan, task, review, conversion and execution action is written to the audit trail with trace ID and actor context.
