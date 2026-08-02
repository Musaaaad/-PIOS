# PIOS MVP Backend v1.4

Sprint 13 institutional pilot execution and outcome reporting. The release adds governed pilot runs, hashed OIDC identity binding, data provenance attestations, governed session execution, operational outcome metrics, adoption events, privacy-safe feedback, and human-approved outcome reports.

## Local verification
```bash
PIOS_ENV=test PIOS_DATABASE_URL=sqlite+pysqlite:///:memory: PIOS_ALLOW_DEV_TOKENS=true pytest -q
PIOS_ENV=test PIOS_DATABASE_URL=sqlite+pysqlite:///:memory: PIOS_ALLOW_DEV_TOKENS=true python scripts/sprint13_institutional_pilot_smoke.py
```

Synthetic or local results are not institutional evidence, CBAHI compliance, or accreditation readiness.
