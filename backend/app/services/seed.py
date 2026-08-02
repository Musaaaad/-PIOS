from __future__ import annotations

import uuid
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.entities import (
    Organization, Site, Role, Standard, MeasurableElement, NestedClause,
    Document, DocumentVersion, DocumentStandardLink, UatScenario
)
from app.schemas.imports import BaselinePayload
from app.services.import_baseline import split_eoc, validate_baseline

NAMESPACE = uuid.UUID("3a36b889-6a3e-4f39-8c2a-c684b495cb61")


def stable_uuid(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{kind}:{key}")


def upsert(session: Session, model, values: dict, conflict_columns: list[str], update_columns: list[str]):
    dialect = session.get_bind().dialect.name
    insert_fn = sqlite_insert if dialect == "sqlite" else pg_insert
    stmt = insert_fn(model).values(**values)
    index_elements = [getattr(model, x) for x in conflict_columns]
    if update_columns:
        stmt = stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_={x: getattr(stmt.excluded, x) for x in update_columns},
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=index_elements)
    session.execute(stmt)


def seed_baseline(session: Session, payload: BaselinePayload, *, commit: bool = True) -> dict[str, int]:
    validation = validate_baseline(payload)
    if not validation.valid:
        raise ValueError(validation.model_dump())

    org_id = stable_uuid("organization", "NBC")
    site_id = stable_uuid("site", "NBC:TGH")
    upsert(session, Organization, {
        "id": org_id, "code": "NBC", "name_ar": "تجمع الحدود الشمالية الصحي",
        "name_en": "Northern Border Health Cluster", "active": True,
    }, ["code"], ["name_ar", "name_en", "active"])
    upsert(session, Site, {
        "id": site_id, "organization_id": org_id, "code": "TGH",
        "name_ar": "مستشفى طريف العام", "name_en": "Turaif General Hospital",
        "site_type": "Hospital", "timezone": "Asia/Riyadh", "active": True,
    }, ["organization_id", "code"], ["name_ar", "name_en", "site_type", "timezone", "active"])

    roles = {
        "SystemAdmin": "مدير النظام", "AccreditationLead": "قائد الاعتماد",
        "PharmacyDirector": "مدير الرعاية الصيدلية", "MedicationSafety": "مسؤول سلامة الدواء",
        "EvidenceCollector": "جامع الأدلة", "EvidenceReviewer": "مراجع الأدلة",
        "MEOwner": "مالك عنصر التقييم", "CAPAOwner": "مالك الإجراء التصحيحي",
        "CAPAVerifier": "متحقق CAPA", "ReadOnlyAuditor": "مدقق للقراءة فقط",
    }
    for code, name_ar in roles.items():
        upsert(session, Role, {
            "id": stable_uuid("role", code), "code": code, "name_ar": name_ar,
            "description": "PIOS MVP baseline role",
        }, ["code"], ["name_ar", "description"])


    uat_scenarios = [
        ("UAT-01", "تسجيل الدخول عبر OIDC ونطاق طريف", "OIDC login and TGH site scope", "Identity", "P0", ["Login with mapped TGH user", "Verify roles and site claim", "Attempt unauthorized mutation"], "Identity is correct and unauthorized action returns 403."),
        ("UAT-02", "التبديل العربي والإنجليزي", "Arabic and English direction switch", "Frontend", "P2", ["Open dashboard in Arabic", "Switch to English", "Inspect tables and mobile view"], "RTL/LTR changes without clipping or hidden controls."),
        ("UAT-03", "منع الأخضر مع P0 أوESR", "False-green prevention", "Readiness", "P0", ["Create P0 finding", "Calculate readiness", "Review dashboard"], "Overall status remains CriticalOpenActions."),
        ("UAT-04", "قائمة العمل المبنية على الدور", "Role-aware worklist", "Workflow", "P1", ["Login as collector", "Review assigned requests", "Login as verifier"], "Each role sees only actionable work for its scope."),
        ("UAT-05", "عدم تكرار التنبيهات", "Notification idempotency", "Notifications", "P1", ["Refresh notifications twice", "Compare fingerprints"], "Second refresh creates no duplicate notification."),
        ("UAT-06", "رفض دليل ESR", "Rejected ESR evidence", "Evidence", "P0", ["Submit ESR evidence", "Fail mandatory review test", "Review finding"], "P0 finding and critical notification are created."),
        ("UAT-07", "فشل اختبار فعالية CAPA", "Failed CAPA effectiveness", "CAPA", "P0", ["Close actions", "Fail effectiveness check", "Review states"], "CAPA and finding reopen automatically."),
        ("UAT-08", "سلامة الحزمة التنفيذية", "Executive export integrity", "Exports", "P1", ["Create executive ZIP", "Verify files", "Verify SHA-256"], "Package contains required files and stored hash matches."),
        ("UAT-09", "صلاحيات المدقق للقراءة", "Read-only auditor", "Security", "P1", ["Login as auditor", "View and export", "Attempt mutation"], "View/export allowed and mutation denied."),
        ("UAT-10", "النسخ الاحتياطي والاستعادة", "Backup and restore", "Runtime", "P0", ["Take backup", "Restore isolated environment", "Compare links and audit"], "Restored data preserves evidence links, audit and workflow state."),
        ("UAT-11", "تهيئة حملة P0 بصورة Idempotent", "Idempotent P0 bootstrap", "Pilot", "P1", ["Bootstrap campaign twice", "Count requests"], "Exactly 48 unique P0 requests exist."),
        ("UAT-12", "بوابة قرار التشغيل", "Go/no-go gate", "Pilot", "P0", ["Leave a required gate failing", "Attempt Go", "Pass all gates and retry"], "Go is blocked until all required gates and critical UAT pass."),
    ]
    for code, ar, en, category, criticality, steps, expected in uat_scenarios:
        upsert(session, UatScenario, {
            "id": stable_uuid("uat-scenario", code), "code": code, "title_ar": ar, "title_en": en,
            "category": category, "criticality": criticality, "steps": steps,
            "expected_result": expected, "active": True,
        }, ["code"], ["title_ar", "title_en", "category", "criticality", "steps", "expected_result", "active"])

    standard_ids: dict[str, uuid.UUID] = {}
    for n in range(1, 42):
        code = f"MM.{n}"
        sid = stable_uuid("standard", code)
        standard_ids[code] = sid
        upsert(session, Standard, {
            "id": sid, "code": code, "title": f"Medication Management Standard {code}",
            "source_version": "CBAHI MM Self-Assessment Tool", "active": True,
        }, ["code"], ["title", "source_version", "active"])

    nested_count = 0
    for row in payload.me_registry:
        me_id = row["me_id"]
        mid = stable_uuid("me", me_id)
        upsert(session, MeasurableElement, {
            "id": mid, "me_id": me_id, "standard_id": standard_ids[row["standard_code"]],
            "official_text": row["official_text"], "eoc": split_eoc(row.get("eoc")),
            "esr": bool(row.get("esr")), "source_page": row.get("source_page"),
            "source_version": str(row.get("version") or "CBAHI MM Self-Assessment Tool"),
            "active": bool(row.get("active", True)),
        }, ["me_id"], ["standard_id", "official_text", "eoc", "esr", "source_page", "source_version", "active"])

        nested = [x.strip() for x in str(row.get("nested_ids", "")).split(",") if x.strip()]
        for clause in nested:
            nested_count += 1
            ordinal = int(clause.rsplit(".", 1)[1])
            upsert(session, NestedClause, {
                "id": stable_uuid("clause", clause), "clause_id": clause,
                "measurable_element_id": mid, "ordinal": ordinal,
            }, ["clause_id"], ["measurable_element_id", "ordinal"])

    for row in payload.documents:
        legacy_id = row["evidence_id"]
        did = stable_uuid("document", legacy_id)
        lifecycle = row.get("lifecycle_status") or "Draft"
        if lifecycle not in {"Draft", "Review", "Approved", "Effective", "Superseded", "Retired"}:
            lifecycle = "Draft"
        upsert(session, Document, {
            "id": did, "organization_id": org_id, "legacy_evidence_id": legacy_id,
            "code": row["document_code"], "title": row["title"],
            "document_type": row.get("document_type") or "Document",
            "lifecycle_status": lifecycle, "overlap_family": row.get("overlap_family") or None,
            "notes": row.get("notes") or None,
        }, ["legacy_evidence_id"], ["code", "title", "document_type", "lifecycle_status", "overlap_family", "notes"])

        version_id = stable_uuid("document-version", legacy_id + ":baseline")
        upsert(session, DocumentVersion, {
            "id": version_id, "document_id": did,
            "version_label": row.get("current_version") or "baseline-unverified",
            "status": lifecycle,
            "source_page_start": row.get("page_start"), "source_page_end": row.get("page_end"),
            "file_uri": row.get("source_file") or None,
        }, ["document_id", "version_label"], ["status", "source_page_start", "source_page_end", "file_uri"])

        standards = [x.strip() for x in str(row.get("related_standards", "")).split(",") if x.strip()]
        for code in standards:
            if code in standard_ids:
                upsert(session, DocumentStandardLink, {
                    "id": stable_uuid("document-standard", f"{legacy_id}:{code}"),
                    "document_id": did, "standard_id": standard_ids[code],
                }, ["document_id", "standard_id"], [])

    if commit:
        session.commit()
    else:
        session.flush()
    return {"standards": 41, "measurable_elements": 266, "nested_clauses": nested_count, "documents": 75, "uat_scenarios": 12}
