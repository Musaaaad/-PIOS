from __future__ import annotations
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    EvidenceCampaign, EvidenceRequest, EvidenceItem, EvidenceFile, EvidenceMeLink,
    EvidenceReviewTest, MeasurableElement
)

CAMPAIGN_TRANSITIONS = {
    "Draft": {"Open", "Cancelled"},
    "Open": {"Closed", "Cancelled"},
    "Closed": set(),
    "Cancelled": set(),
}
MANDATORY_REVIEW_TESTS = {
    "AUTHENTICITY", "CURRENCY", "SCOPE", "REPRESENTATIVENESS",
    "TRACEABILITY", "CONSISTENCY", "EOC_MATCH",
}


def transition_campaign(campaign: EvidenceCampaign, to_status: str) -> tuple[dict, dict]:
    if to_status not in CAMPAIGN_TRANSITIONS.get(campaign.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid campaign transition: {campaign.status} -> {to_status}")
    before = {"status": campaign.status}
    now = datetime.now(timezone.utc)
    campaign.status = to_status
    if to_status == "Open":
        campaign.opened_at = now
    if to_status in {"Closed", "Cancelled"}:
        campaign.closed_at = now
    return before, {"status": campaign.status}


def validate_evidence_submission(db: Session, item: EvidenceItem) -> dict:
    if item.status != "Draft":
        raise HTTPException(status_code=409, detail="Only Draft evidence can be submitted")
    if item.period_start and item.period_end and item.period_end < item.period_start:
        raise HTTPException(status_code=422, detail="Evidence period is invalid")
    links = list(db.scalars(select(EvidenceMeLink).where(EvidenceMeLink.evidence_item_id == item.id)).all())
    files = list(db.scalars(select(EvidenceFile).where(EvidenceFile.evidence_item_id == item.id)).all())
    if not links:
        raise HTTPException(status_code=409, detail="Evidence must be linked to at least one measurable element")
    clean_files = [x for x in files if x.scan_status == "Clean"]
    has_structured = bool(item.structured_data) or bool((item.description or "").strip())
    if not clean_files and not has_structured:
        raise HTTPException(status_code=409, detail="Evidence requires a clean file or structured content")
    rejected_files = [x for x in files if x.scan_status != "Clean"]
    if rejected_files:
        raise HTTPException(status_code=409, detail="Evidence contains files that did not pass scanning")
    return {
        "me_link_count": len(links), "file_count": len(files),
        "clean_file_count": len(clean_files), "has_structured_content": has_structured,
    }


def validate_review_payload(db: Session, item: EvidenceItem, verdict: str, tests: list[dict]) -> dict[str, str]:
    if item.status not in {"Submitted", "UnderReview"}:
        raise HTTPException(status_code=409, detail="Evidence must be Submitted or UnderReview before review")
    test_map = {x["test_code"]: x["result"] for x in tests}
    if set(test_map) != MANDATORY_REVIEW_TESTS:
        missing = sorted(MANDATORY_REVIEW_TESTS - set(test_map))
        extra = sorted(set(test_map) - MANDATORY_REVIEW_TESTS)
        raise HTTPException(status_code=422, detail={"missing_tests": missing, "extra_tests": extra})
    if verdict == "Accepted" and any(v != "Pass" for v in test_map.values()):
        raise HTTPException(status_code=409, detail="Accepted verdict requires all mandatory review tests to Pass")
    if verdict in {"Partial", "Rejected", "Contradictory", "Expired"} and all(v == "Pass" for v in test_map.values()):
        raise HTTPException(status_code=409, detail=f"{verdict} verdict requires at least one failed or non-applicable test")
    return test_map


def request_status_for_verdict(verdict: str) -> str:
    return {
        "Accepted": "Accepted", "Partial": "PartiallyAccepted", "Rejected": "Rejected",
        "Contradictory": "Contradictory", "Expired": "Expired",
    }[verdict]


def item_status_for_verdict(verdict: str) -> str:
    return {
        "Accepted": "Accepted", "Partial": "PartiallyAccepted", "Rejected": "Rejected",
        "Contradictory": "Contradictory", "Expired": "Expired",
    }[verdict]
