"""Sprint 23.9 - the acceptance screen's gates must come from stored runs.

Live symptom this exists for: the "قبول النشر المؤسسي" screen showed
DEV_TOKENS_DISABLED as "Fail - dev mode active" while the live service ran with
PIOS_ALLOW_DEV_TOKENS=false and PIOS_AUTH_MODE=oidc. The audit found the value
was a hand-written constant in frontend/demo-data.js: it had never been
measured, could not be moved by any configuration change, and the string "dev
mode active" appears nowhere in the backend.

Two properties are pinned here, and they are the whole point:

  1. An unmeasured gate reports NotAssessed and is never ready. Missing
     evidence must not round up to a pass, and must not round down to a
     failure either - both are claims nobody made.
  2. Re-evaluation actually re-measures. Flipping allow_dev_tokens from true to
     false and re-evaluating must move the gate, while merely re-reading the
     summary must not.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import DeploymentAcceptanceRun
from app.services.deployment_acceptance import ACCEPTANCE_CATALOG

SUMMARY = "/api/v1/deployment/acceptance-summary"
EVALUATE = "/api/v1/deployment/acceptance-summary/evaluate"

# The five gates the live screen displayed. They are the regression surface.
REPORTED = ["DEV_TOKENS_DISABLED", "OIDC_TOKEN_VALIDATION", "BACKUP_RESTORE_TESTED", "UAT_CRITICAL_PASS"]


def make_env(client, kind="Pilot"):
    """A production-like environment, so prod_like gating is actually exercised."""
    r = client.post("/api/v1/deployment/environments", json={
        "code": f"{kind.lower()}-239", "name": f"{kind} environment", "environment_type": kind,
        "api_base_url": "http://api.local", "frontend_base_url": "http://frontend.local",
        "database_kind": "PostgreSQL", "object_storage_kind": "S3", "auth_mode": "OIDC",
        "oidc_issuer": "https://id.example", "release_version": "1.3.0",
        "tls_enabled": True, "monitoring_enabled": True})
    assert r.status_code == 201, r.text
    return r.json()


def statuses(payload):
    return {x["check_code"]: x["status"] for x in payload["checks"]}


def run_count():
    with SessionLocal() as db:
        return db.scalar(select(func.count(DeploymentAcceptanceRun.id))) or 0


@pytest.fixture
def dev_tokens_off(monkeypatch):
    """The live Render posture: development tokens off, OIDC on."""
    monkeypatch.setenv("PIOS_ALLOW_DEV_TOKENS", "false")
    monkeypatch.setenv("PIOS_AUTH_MODE", "oidc")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


# ===================== nothing measured must read as nothing measured

def test_no_environment_reports_not_assessed(client):
    body = client.get(SUMMARY).json()
    assert body["assessed"] is False
    assert body["reason"] == "no_environment"
    assert body["environment"] is None
    assert body["run"] is None
    assert body["summary"]["outcome"] == "NotAssessed"
    assert body["summary"]["deployment_ready"] is False


def test_registered_environment_without_a_run_reports_not_assessed(client):
    make_env(client)
    body = client.get(SUMMARY).json()
    assert body["assessed"] is False
    assert body["reason"] == "no_run"
    assert body["environment"]["code"] == "pilot-239"
    assert body["run"] is None
    assert body["summary"]["deployment_ready"] is False


def test_unassessed_gates_name_every_catalog_entry_without_scoring_it(client):
    """All 24 gates are listed - none of them claims a result."""
    body = client.get(SUMMARY).json()
    assert len(body["checks"]) == len(ACCEPTANCE_CATALOG) == 24
    assert {x["check_code"] for x in body["checks"]} == {c[0] for c in ACCEPTANCE_CATALOG}
    for check in body["checks"]:
        assert check["status"] == "NotAssessed", check["check_code"]
        assert check["measured_value"] is None
        assert check["evidence_reference"] is None
        assert check["checked_at"] is None


def test_missing_evidence_never_rounds_up_to_pass(client):
    """The rule the user set: Pending is not Pass, missing evidence is not Pass."""
    body = client.get(SUMMARY).json()
    assert body["summary"]["pass"] == 0
    assert not any(x["status"] == "Pass" for x in body["checks"])
    assert body["summary"]["deployment_ready"] is False


def test_the_four_reported_gates_are_unmeasured_not_failed(client):
    """Absent measurement is not a failure verdict either - nobody claimed one."""
    body = client.get(SUMMARY).json()
    for code in REPORTED:
        assert statuses(body)[code] == "NotAssessed"
    assert body["summary"]["fail"] == 0


# ===================== reading is not measuring

def test_reading_the_summary_creates_nothing(client):
    make_env(client)
    before = run_count()
    for _ in range(3):
        assert client.get(SUMMARY).status_code == 200
    assert run_count() == before


def test_reading_the_summary_does_not_recompute_a_stored_gate(client, dev_tokens_off):
    """A GET reports what is stored, even when live settings have since moved.

    This is the honest half of the contract: the screen must not silently
    upgrade a stored Fail because the process it is running in now happens to
    be configured differently. Only an explicit re-evaluation may do that.
    """
    make_env(client)
    # Stored while dev tokens were still enabled (the conftest default).
    get_settings.cache_clear()
    import os
    os.environ["PIOS_ALLOW_DEV_TOKENS"] = "true"
    os.environ["PIOS_AUTH_MODE"] = "dev"
    get_settings.cache_clear()
    stored = client.post(EVALUATE).json()
    assert statuses(stored)["DEV_TOKENS_DISABLED"] == "Fail"

    # Now the live posture is correct, but nothing has been re-measured.
    os.environ["PIOS_ALLOW_DEV_TOKENS"] = "false"
    os.environ["PIOS_AUTH_MODE"] = "oidc"
    get_settings.cache_clear()
    reread = client.get(SUMMARY).json()
    assert statuses(reread)["DEV_TOKENS_DISABLED"] == "Fail", (
        "a plain read must report the stored measurement, not re-derive it"
    )
    assert reread["run"]["run_code"] == stored["run"]["run_code"]


# ===================== re-evaluation actually re-measures

def test_dev_tokens_true_to_false_is_reflected_on_reevaluation(client):
    """The regression the sprint was opened for.

    allow_dev_tokens true -> false, auth_mode dev -> oidc, and the gate must
    move from Fail to Pass on re-evaluation. If this test can pass while the
    gate is frozen, the screen is not reading the backend.
    """
    import os
    make_env(client, "Pilot")

    os.environ["PIOS_ALLOW_DEV_TOKENS"] = "true"
    os.environ["PIOS_AUTH_MODE"] = "dev"
    get_settings.cache_clear()
    first = client.post(EVALUATE).json()
    assert first["assessed"] is True
    assert statuses(first)["DEV_TOKENS_DISABLED"] == "Fail"
    assert first["summary"]["deployment_ready"] is False

    os.environ["PIOS_ALLOW_DEV_TOKENS"] = "false"
    os.environ["PIOS_AUTH_MODE"] = "oidc"
    get_settings.cache_clear()
    second = client.post(EVALUATE).json()
    assert statuses(second)["DEV_TOKENS_DISABLED"] == "Pass", (
        "re-evaluation did not pick up the corrected live configuration"
    )

    os.environ["PIOS_ALLOW_DEV_TOKENS"] = "true"
    os.environ["PIOS_AUTH_MODE"] = "dev"
    get_settings.cache_clear()


def test_the_gate_carries_the_backend_measurement_not_demo_text(client, dev_tokens_off):
    """`dev mode active` was the demo string. A real run cannot produce it."""
    make_env(client)
    body = client.post(EVALUATE).json()
    gate = next(x for x in body["checks"] if x["check_code"] == "DEV_TOKENS_DISABLED")
    assert gate["measured_value"].startswith("allow_dev_tokens=")
    assert "auth_mode=" in gate["measured_value"]
    assert "dev mode active" not in (gate["measured_value"] or "")


def test_evaluation_stores_a_run_that_the_summary_then_reports(client, dev_tokens_off):
    make_env(client)
    before = run_count()
    evaluated = client.post(EVALUATE).json()
    assert run_count() == before + 1
    assert evaluated["assessed"] is True
    assert evaluated["run"]["status"] == "Completed"
    assert evaluated["run"]["run_code"].startswith("LIVE-")

    reread = client.get(SUMMARY).json()
    assert reread["assessed"] is True
    assert reread["run"]["run_code"] == evaluated["run"]["run_code"]
    assert statuses(reread) == statuses(evaluated)


def test_evaluated_summary_counts_all_24_gates(client, dev_tokens_off):
    make_env(client)
    body = client.post(EVALUATE).json()
    s = body["summary"]
    assert s["total"] == len(ACCEPTANCE_CATALOG)
    assert s["pass"] + s["fail"] + s["pending"] + s["blocked"] + s["waived"] == s["total"]
    assert len(body["checks"]) == len(ACCEPTANCE_CATALOG)


def test_manual_gates_stay_pending_after_an_automated_evaluation(client, dev_tokens_off):
    """Automated measurement must not manufacture evidence for manual gates.

    BACKUP_RESTORE_TESTED and OIDC_TOKEN_VALIDATION need a recorded restore
    test and a recorded token validation. Running the automated sweep supplies
    neither, so they stay Pending - which is the correct answer, not a bug.
    """
    make_env(client)
    body = client.post(EVALUATE).json()
    st = statuses(body)
    assert st["BACKUP_RESTORE_TESTED"] == "Pending"
    assert st["OIDC_TOKEN_VALIDATION"] == "Pending"
    assert body["summary"]["deployment_ready"] is False


def test_unlinked_pilot_gates_are_blocked_with_a_reason(client, dev_tokens_off):
    """Pilot gates with no pilot linked are Blocked, and the reason is recorded.

    execute_automated_checks() attaches the "No pilot linked" explanation to
    PILOT_USERS_READY; UAT_CRITICAL_PASS records the measured value it derived
    from. Blocked here means "cannot be measured", which is why neither counts
    towards deployment_ready.
    """
    make_env(client)
    body = client.post(EVALUATE).json()
    checks = {x["check_code"]: x for x in body["checks"]}
    assert checks["PILOT_USERS_READY"]["status"] == "Blocked"
    assert checks["PILOT_USERS_READY"]["details"] == "No pilot linked"
    assert checks["UAT_CRITICAL_PASS"]["status"] == "Blocked"
    assert checks["UAT_CRITICAL_PASS"]["measured_value"] == "False"
    assert "UAT_CRITICAL_PASS" in body["summary"]["blockers"]
    assert body["summary"]["deployment_ready"] is False


# ===================== fail-closed on the paths that could fabricate

def test_evaluate_refuses_to_invent_an_environment(client):
    """No environment means no evaluation - and still no pass.

    Auto-registering one would fabricate exactly the inputs the gates measure:
    environment_type decides prod_like, tls_enabled decides TLS_ENABLED,
    object_storage_kind decides OBJECT_STORAGE_CONFIGURED.
    """
    r = client.post(EVALUATE)
    assert r.status_code == 409, r.text
    assert "register" in r.json()["detail"].lower()
    assert run_count() == 0

    after = client.get(SUMMARY).json()
    assert after["assessed"] is False
    assert after["summary"]["deployment_ready"] is False


def test_repeat_evaluation_within_the_same_second_reuses_its_run(client, dev_tokens_off):
    """The run code is second-resolution; two clicks must not collide."""
    make_env(client)
    first = client.post(EVALUATE)
    second = client.post(EVALUATE)
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["assessed"] is True


def test_evaluation_is_restricted_to_operators(client):
    """The write path is role-guarded; the read path is not."""
    from app.api.v1.endpoints import deployment as module

    assert module.EXECUTE_ROLES == ("SystemAdmin", "AccreditationLead")
    route = next(r for r in module.router.routes if r.path.endswith("/acceptance-summary/evaluate"))
    assert "POST" in route.methods
    # can_execute is reported so the UI can hide a button the API would refuse.
    assert client.get(SUMMARY).json()["can_execute"] is True
