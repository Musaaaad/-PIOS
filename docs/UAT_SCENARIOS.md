# Sprint 4 UAT Scenarios

| ID | Scenario | Expected result |
|---|---|---|
| UAT-01 | OIDC login with TGH role claims | Identity and site scope appear; unauthorized roles receive 403. |
| UAT-02 | Arabic/English switch | Direction, labels and tables switch without clipping. |
| UAT-03 | Dashboard with P0 and ESR red | Overall status remains CriticalOpenActions regardless of readiness score. |
| UAT-04 | Collector worklist | Only relevant evidence requests appear with due dates and severity. |
| UAT-05 | Notification refresh twice | Second refresh creates no duplicate fingerprint. |
| UAT-06 | Evidence rejected for ESR | P0 Finding and critical notification are created. |
| UAT-07 | CAPA effectiveness failure | Finding and CAPA reopen automatically. |
| UAT-08 | Executive export | ZIP contains readiness, findings, CAPA, audit and metadata; SHA-256 recorded. |
| UAT-09 | Read-only auditor | Can view/export but cannot mutate workflow. |
| UAT-10 | Backup/restore | Restored environment preserves evidence links, audit and export metadata. |
