from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import (
    EvidenceCampaign, EvidenceRequest, Finding, MeasurableElement, Organization, Site,
    Notification, ReadinessSnapshot,
)
from app.services.readiness import calculate_readiness


def ids(db):
    org = db.scalar(select(Organization).where(Organization.code == "NBC"))
    site = db.scalar(select(Site).where(Site.code == "TGH"))
    me = db.scalar(select(MeasurableElement).where(MeasurableElement.me_id == "MM.5.1"))
    return org, site, me


def test_dashboard_and_worklist(client):
    with SessionLocal() as db:
        _, site, me = ids(db)
        campaign = EvidenceCampaign(site_id=site.id, name="Q3", period_start=date.today(), period_end=date.today(), status="Open")
        db.add(campaign); db.flush()
        db.add(EvidenceRequest(campaign_id=campaign.id, measurable_element_id=me.id, eoc=["D"], tool_code="D", due_at=datetime.now(timezone.utc)-timedelta(days=1), status="Requested"))
        db.add(Finding(site_id=site.id, measurable_element_id=me.id, criterion="ESR", severity="P0", problem_statement="HAM control missing", status="Open", due_date=date.today()-timedelta(days=1)))
        db.flush(); calculate_readiness(db, site.id, "Q3"); db.commit()
    r = client.get("/api/v1/dashboard/overview")
    assert r.status_code == 200
    body = r.json(); assert body["findings"]["by_severity"]["P0"] == 1
    assert body["evidence"]["overdue_requests"] == 1
    r = client.get("/api/v1/worklists/my")
    assert r.status_code == 200 and r.json()["total"] >= 2


def test_notifications_refresh_and_update(client):
    with SessionLocal() as db:
        _, site, me = ids(db)
        db.add(Finding(site_id=site.id, measurable_element_id=me.id, criterion="ESR", severity="P0", problem_statement="Critical", status="Open"))
        db.commit()
    r = client.post("/api/v1/notifications/refresh")
    assert r.status_code == 200 and r.json()["created"] >= 1
    rows = client.get("/api/v1/notifications").json()
    assert rows and rows[0]["status"] == "Unread"
    r = client.patch(f"/api/v1/notifications/{rows[0]['id']}", json={"status":"Read"})
    assert r.status_code == 200 and r.json()["status"] == "Read"


def test_exports_readiness_and_executive_pack(client, tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings(); monkeypatch.setattr(settings, "export_storage_root", str(tmp_path))
    with SessionLocal() as db:
        _, site, _ = ids(db); calculate_readiness(db, site.id, "Q3"); db.commit()
    r = client.post("/api/v1/exports", json={"export_type":"readiness","file_format":"csv","filters":{}})
    assert r.status_code == 201, r.text
    job = r.json(); assert job["status"] == "Completed" and job["size_bytes"] > 0
    d = client.get(f"/api/v1/exports/{job['id']}/download")
    assert d.status_code == 200 and b"me_id" in d.content
    r = client.post("/api/v1/exports", json={"export_type":"executive_pack","file_format":"zip","filters":{}})
    assert r.status_code == 201 and r.json()["file_format"] == "zip"


def test_identity_dev_token(client):
    r = client.get("/api/v1/identity/me", headers={"Authorization":"Bearer dev:qa-user:AccreditationLead,ReadOnlyAuditor"})
    assert r.status_code == 200
    assert r.json()["user_id"] == "qa-user" and "AccreditationLead" in r.json()["roles"]
