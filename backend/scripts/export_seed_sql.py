from __future__ import annotations
import json, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "seeds" / "PIOS_MVP_Import_Data_v1.json").read_text(encoding="utf-8"))
out = ROOT / "sql" / "002_seed_baseline.sql"
NS = uuid.UUID("3a36b889-6a3e-4f39-8c2a-c684b495cb61")

def uid(kind, key): return str(uuid.uuid5(NS, f"{kind}:{key}"))
def q(value):
    if value is None: return "NULL"
    if isinstance(value, bool): return "TRUE" if value else "FALSE"
    if isinstance(value, int): return str(value)
    return "'" + str(value).replace("'", "''") + "'"

def jsonb(value):
    return q(json.dumps(value, ensure_ascii=False)) + "::jsonb"

def eoc(value):
    return [x.strip() for x in str(value or "").split(",") if x.strip()]

org_id = uid("organization", "NBC")
site_id = uid("site", "NBC:TGH")
lines = ["-- PIOS MVP baseline seed v1.3", "BEGIN;"]
lines.append(f"INSERT INTO organizations (id,code,name_ar,name_en,active) VALUES ({q(org_id)}::uuid,'NBC','تجمع الحدود الشمالية الصحي','Northern Border Health Cluster',TRUE) ON CONFLICT (code) DO UPDATE SET name_ar=EXCLUDED.name_ar,name_en=EXCLUDED.name_en,active=EXCLUDED.active;")
lines.append(f"INSERT INTO sites (id,organization_id,code,name_ar,name_en,site_type,timezone,active) VALUES ({q(site_id)}::uuid,{q(org_id)}::uuid,'TGH','مستشفى طريف العام','Turaif General Hospital','Hospital','Asia/Riyadh',TRUE) ON CONFLICT (organization_id,code) DO UPDATE SET name_ar=EXCLUDED.name_ar,name_en=EXCLUDED.name_en,active=EXCLUDED.active;")
roles = {"SystemAdmin":"مدير النظام","AccreditationLead":"قائد الاعتماد","PharmacyDirector":"مدير الرعاية الصيدلية","MedicationSafety":"مسؤول سلامة الدواء","EvidenceCollector":"جامع الأدلة","EvidenceReviewer":"مراجع الأدلة","MEOwner":"مالك عنصر التقييم","CAPAOwner":"مالك الإجراء التصحيحي","CAPAVerifier":"متحقق CAPA","ReadOnlyAuditor":"مدقق للقراءة فقط"}
for code, ar in roles.items():
    rid=uid('role',code)
    lines.append(f"INSERT INTO roles (id,code,name_ar,description) VALUES ({q(rid)}::uuid,{q(code)},{q(ar)},'PIOS MVP baseline role') ON CONFLICT (code) DO UPDATE SET name_ar=EXCLUDED.name_ar,description=EXCLUDED.description;")

uat_scenarios = [
    ("UAT-01","تسجيل الدخول عبر OIDC ونطاق طريف","OIDC login and TGH site scope","Identity","P0",["Login with mapped TGH user","Verify roles and site claim","Attempt unauthorized mutation"],"Identity is correct and unauthorized action returns 403."),
    ("UAT-02","التبديل العربي والإنجليزي","Arabic and English direction switch","Frontend","P2",["Open dashboard in Arabic","Switch to English","Inspect tables and mobile view"],"RTL/LTR changes without clipping or hidden controls."),
    ("UAT-03","منع الأخضر مع P0 أوESR","False-green prevention","Readiness","P0",["Create P0 finding","Calculate readiness","Review dashboard"],"Overall status remains CriticalOpenActions."),
    ("UAT-04","قائمة العمل المبنية على الدور","Role-aware worklist","Workflow","P1",["Login as collector","Review assigned requests","Login as verifier"],"Each role sees only actionable work for its scope."),
    ("UAT-05","عدم تكرار التنبيهات","Notification idempotency","Notifications","P1",["Refresh notifications twice","Compare fingerprints"],"Second refresh creates no duplicate notification."),
    ("UAT-06","رفض دليل ESR","Rejected ESR evidence","Evidence","P0",["Submit ESR evidence","Fail mandatory review test","Review finding"],"P0 finding and critical notification are created."),
    ("UAT-07","فشل اختبار فعالية CAPA","Failed CAPA effectiveness","CAPA","P0",["Close actions","Fail effectiveness check","Review states"],"CAPA and finding reopen automatically."),
    ("UAT-08","سلامة الحزمة التنفيذية","Executive export integrity","Exports","P1",["Create executive ZIP","Verify files","Verify SHA-256"],"Package contains required files and stored hash matches."),
    ("UAT-09","صلاحيات المدقق للقراءة","Read-only auditor","Security","P1",["Login as auditor","View and export","Attempt mutation"],"View/export allowed and mutation denied."),
    ("UAT-10","النسخ الاحتياطي والاستعادة","Backup and restore","Runtime","P0",["Take backup","Restore isolated environment","Compare links and audit"],"Restored data preserves evidence links, audit and workflow state."),
    ("UAT-11","تهيئة حملة P0 بصورة Idempotent","Idempotent P0 bootstrap","Pilot","P1",["Bootstrap campaign twice","Count requests"],"Exactly 48 unique P0 requests exist."),
    ("UAT-12","بوابة قرار التشغيل","Go/no-go gate","Pilot","P0",["Leave a required gate failing","Attempt Go","Pass all gates and retry"],"Go is blocked until all required gates and critical UAT pass."),
]
for code, ar, en, category, criticality, steps, expected in uat_scenarios:
    sid=uid('uat-scenario',code)
    lines.append(f"INSERT INTO uat_scenarios (id,code,title_ar,title_en,category,criticality,steps,expected_result,active) VALUES ({q(sid)}::uuid,{q(code)},{q(ar)},{q(en)},{q(category)},{q(criticality)},{jsonb(steps)},{q(expected)},TRUE) ON CONFLICT (code) DO UPDATE SET title_ar=EXCLUDED.title_ar,title_en=EXCLUDED.title_en,category=EXCLUDED.category,criticality=EXCLUDED.criticality,steps=EXCLUDED.steps,expected_result=EXCLUDED.expected_result,active=EXCLUDED.active;")

for n in range(1,42):
    code=f'MM.{n}'; sid=uid('standard',code)
    lines.append(f"INSERT INTO standards (id,code,title,source_version,active) VALUES ({q(sid)}::uuid,{q(code)},{q('Medication Management Standard '+code)},'CBAHI MM Self-Assessment Tool',TRUE) ON CONFLICT (code) DO UPDATE SET title=EXCLUDED.title,source_version=EXCLUDED.source_version,active=EXCLUDED.active;")
for row in data['me_registry']:
    mid=uid('me',row['me_id']); sid=uid('standard',row['standard_code'])
    vals=[f"{q(mid)}::uuid",q(row['me_id']),f"{q(sid)}::uuid",q(row['official_text']),jsonb(eoc(row.get('eoc'))),q(bool(row.get('esr'))),q(row.get('source_page')),q(str(row.get('version') or 'CBAHI MM Self-Assessment Tool')),q(bool(row.get('active',True)))]
    lines.append("INSERT INTO measurable_elements (id,me_id,standard_id,official_text,eoc,esr,source_page,source_version,active) VALUES ("+",".join(vals)+") ON CONFLICT (me_id) DO UPDATE SET standard_id=EXCLUDED.standard_id,official_text=EXCLUDED.official_text,eoc=EXCLUDED.eoc,esr=EXCLUDED.esr,source_page=EXCLUDED.source_page,source_version=EXCLUDED.source_version,active=EXCLUDED.active;")
    for clause in [x.strip() for x in str(row.get('nested_ids','')).split(',') if x.strip()]:
        cid=uid('clause',clause); ordinal=int(clause.rsplit('.',1)[1])
        lines.append(f"INSERT INTO nested_clauses (id,clause_id,measurable_element_id,ordinal) VALUES ({q(cid)}::uuid,{q(clause)},{q(mid)}::uuid,{ordinal}) ON CONFLICT (clause_id) DO UPDATE SET measurable_element_id=EXCLUDED.measurable_element_id,ordinal=EXCLUDED.ordinal;")
for row in data['documents']:
    legacy=row['evidence_id']; did=uid('document',legacy); vid=uid('document-version',legacy+':baseline')
    lifecycle=row.get('lifecycle_status') or 'Draft'
    if lifecycle not in {'Draft','Review','Approved','Effective','Superseded','Retired'}: lifecycle='Draft'
    vals=[f"{q(did)}::uuid",f"{q(org_id)}::uuid",q(legacy),q(row['document_code']),q(row['title']),q(row.get('document_type') or 'Document'),q(lifecycle),q(row.get('overlap_family') or None),q(row.get('notes') or None)]
    lines.append("INSERT INTO documents (id,organization_id,legacy_evidence_id,code,title,document_type,lifecycle_status,overlap_family,notes) VALUES ("+",".join(vals)+") ON CONFLICT (legacy_evidence_id) DO UPDATE SET code=EXCLUDED.code,title=EXCLUDED.title,document_type=EXCLUDED.document_type,lifecycle_status=EXCLUDED.lifecycle_status,overlap_family=EXCLUDED.overlap_family,notes=EXCLUDED.notes;")
    vals=[f"{q(vid)}::uuid",f"{q(did)}::uuid",q(row.get('current_version') or 'baseline-unverified'),q(lifecycle),q(row.get('page_start')),q(row.get('page_end')),q(row.get('source_file') or None)]
    lines.append("INSERT INTO document_versions (id,document_id,version_label,status,source_page_start,source_page_end,file_uri) VALUES ("+",".join(vals)+") ON CONFLICT (document_id,version_label) DO UPDATE SET status=EXCLUDED.status,source_page_start=EXCLUDED.source_page_start,source_page_end=EXCLUDED.source_page_end,file_uri=EXCLUDED.file_uri;")
    for code in [x.strip() for x in str(row.get('related_standards','')).split(',') if x.strip()]:
        link=uid('document-standard',legacy+':'+code); sid=uid('standard',code)
        lines.append(f"INSERT INTO document_standard_links (id,document_id,standard_id) VALUES ({q(link)}::uuid,{q(did)}::uuid,{q(sid)}::uuid) ON CONFLICT (document_id,standard_id) DO NOTHING;")
lines.extend(["COMMIT;", "-- Expected baseline: 41 standards, 266 MEs, 63 nested clauses, 75 documents, 12 UAT scenarios."])
out.write_text("\n".join(lines)+"\n",encoding='utf-8')
print(out)
