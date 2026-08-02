from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import (
    MeasurableElement, EvidenceMeLink, EvidenceItem, Finding,
    ApplicabilityDecision, ReadinessSnapshot, ReadinessSnapshotItem,
)

SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
OPEN_FINDING_STATUSES = {"Open", "Acknowledged", "CAPAOpen", "VerificationPending", "Reopened"}


def calculate_readiness(db: Session, site_id, period_label: str) -> ReadinessSnapshot:
    mes = list(db.scalars(select(MeasurableElement).where(MeasurableElement.active.is_(True)).order_by(MeasurableElement.me_id)).all())
    decisions = {x.measurable_element_id: x for x in db.scalars(
        select(ApplicabilityDecision).where(ApplicabilityDecision.site_id == site_id)
    ).all()}

    evidence_by_me = defaultdict(list)
    for me_id, status in db.execute(
        select(EvidenceMeLink.measurable_element_id, EvidenceItem.status)
        .join(EvidenceItem, EvidenceItem.id == EvidenceMeLink.evidence_item_id)
        .where(EvidenceItem.site_id == site_id)
    ).all():
        evidence_by_me[me_id].append(status)

    findings_by_me = defaultdict(list)
    for finding in db.scalars(select(Finding).where(Finding.site_id == site_id)).all():
        if finding.status in OPEN_FINDING_STATUSES:
            findings_by_me[finding.measurable_element_id].append(finding)

    totals = {
        "total": len(mes), "applicable": 0, "na": 0, "sufficient": 0,
        "partial": 0, "missing": 0, "p0": 0, "p1": 0, "p2": 0,
    }
    item_payloads = []
    esr_groups = defaultdict(lambda: {"total": 0, "sufficient": 0, "open_critical": 0})

    for me in mes:
        decision = decisions.get(me.id)
        applicability = decision.decision if decision else "Applicable"
        if applicability == "NotApplicable":
            totals["na"] += 1
            evidence_status = "NotRequired"
            readiness_state = "NotApplicable"
            rationale = "Approved NotApplicable decision; excluded from denominator."
            open_findings = []
            highest = None
        else:
            totals["applicable"] += 1
            statuses = evidence_by_me.get(me.id, [])
            if "Accepted" in statuses:
                evidence_status = "Accepted"
            elif any(x in {"PartiallyAccepted", "Submitted", "UnderReview"} for x in statuses):
                evidence_status = "Partial"
            else:
                evidence_status = "Missing"
            open_findings = findings_by_me.get(me.id, [])
            highest = min((x.severity for x in open_findings), key=lambda x: SEVERITY_ORDER.get(x, 99), default=None)
            if highest == "P0":
                readiness_state = "CriticalBlocked"
                rationale = "Open P0 finding prevents a green readiness state."
            elif highest == "P1":
                readiness_state = "Blocked"
                rationale = "Open P1 finding requires closure before evidence readiness."
            elif evidence_status == "Accepted":
                readiness_state = "EvidenceSufficient"
                rationale = "Accepted evidence exists and no open P0/P1 finding is present."
            elif evidence_status == "Partial":
                readiness_state = "Partial"
                rationale = "Evidence exists but is not fully accepted."
            else:
                readiness_state = "Missing"
                rationale = "No accepted or partial evidence is linked."

            if evidence_status == "Accepted" and highest not in {"P0", "P1"}:
                totals["sufficient"] += 1
            elif evidence_status == "Partial":
                totals["partial"] += 1
            else:
                totals["missing"] += 1
            for finding in open_findings:
                if finding.severity == "P0": totals["p0"] += 1
                elif finding.severity == "P1": totals["p1"] += 1
                elif finding.severity == "P2": totals["p2"] += 1

        if me.esr:
            standard = ".".join(me.me_id.split(".")[:2])
            esr_groups[standard]["total"] += 1
            if readiness_state == "EvidenceSufficient":
                esr_groups[standard]["sufficient"] += 1
            if highest in {"P0", "P1"} or readiness_state in {"CriticalBlocked", "Blocked"}:
                esr_groups[standard]["open_critical"] += 1

        item_payloads.append({
            "measurable_element_id": me.id,
            "applicability": applicability,
            "evidence_status": evidence_status,
            "open_findings": len(open_findings),
            "highest_severity": highest,
            "readiness_state": readiness_state,
            "rationale": rationale,
        })

    esr_status = {}
    esr_not_green = False
    for code in ["MM.5", "MM.6", "MM.41"]:
        row = dict(esr_groups[code])
        if row["open_critical"] > 0:
            row["status"] = "Red"
        elif row["sufficient"] == row["total"] and row["total"] > 0:
            row["status"] = "Green"
        else:
            row["status"] = "Amber"
        esr_not_green = esr_not_green or row["status"] != "Green"
        esr_status[code] = row

    score = int(round(totals["sufficient"] / totals["applicable"] * 100)) if totals["applicable"] else 100
    critical = totals["p0"] > 0 or esr_not_green
    if critical:
        overall = "CriticalOpenActions"
    elif totals["p1"] > 0 or score < 85:
        overall = "NeedsImprovement"
    else:
        overall = "EvidenceReady"

    snapshot = ReadinessSnapshot(
        site_id=site_id, period_label=period_label,
        total_me=totals["total"], applicable_me=totals["applicable"], not_applicable_me=totals["na"],
        evidence_sufficient_me=totals["sufficient"], evidence_partial_me=totals["partial"], evidence_missing_me=totals["missing"],
        open_p0=totals["p0"], open_p1=totals["p1"], open_p2=totals["p2"],
        critical_open_actions=critical, overall_status=overall, esr_status=esr_status,
        details={"score_type": "Evidence readiness, not CBAHI compliance", "publishable_green": not critical, "denominator": totals["applicable"]},
        calculation_version="1.0", readiness_score=score,
    )
    db.add(snapshot); db.flush()
    for payload in item_payloads:
        db.add(ReadinessSnapshotItem(snapshot_id=snapshot.id, **payload))
    return snapshot
