from __future__ import annotations

import re
from collections import Counter
from typing import Any
from app.schemas.imports import BaselinePayload, ImportValidationResult

ME_RE = re.compile(r"^MM\.\d+\.\d+$")
CLAUSE_RE = re.compile(r"^MM\.\d+\.\d+\.\d+$")
VALID_EOC = {"D", "O", "I", "PF", "OMR", "PH", "THC"}


def split_eoc(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in str(value or "").split(",") if x.strip()]


def validate_baseline(payload: BaselinePayload) -> ImportValidationResult:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    me_ids = [row.get("me_id") for row in payload.me_registry]
    if len(me_ids) != 266:
        errors.append({"code": "ME_COUNT", "message": f"Expected 266 MEs; found {len(me_ids)}"})
    duplicates = [key for key, count in Counter(me_ids).items() if count > 1]
    if duplicates:
        errors.append({"code": "ME_DUPLICATE", "values": duplicates})

    nested_total = 0
    esr_standards: set[str] = set()
    for idx, row in enumerate(payload.me_registry, start=1):
        me_id = row.get("me_id", "")
        if not ME_RE.match(me_id):
            errors.append({"code": "ME_FORMAT", "row": idx, "value": me_id})
        eoc = split_eoc(row.get("eoc"))
        unknown = sorted(set(eoc) - VALID_EOC)
        if unknown:
            errors.append({"code": "EOC_UNKNOWN", "row": idx, "values": unknown})
        nested = [x.strip() for x in str(row.get("nested_ids", "")).split(",") if x.strip()]
        nested_total += len(nested)
        for clause in nested:
            if not CLAUSE_RE.match(clause) or not clause.startswith(me_id + "."):
                errors.append({"code": "CLAUSE_FORMAT", "row": idx, "value": clause})
        if row.get("esr"):
            esr_standards.add(".".join(me_id.split(".")[:2]))

    if nested_total != 63:
        errors.append({"code": "CLAUSE_COUNT", "message": f"Expected 63 nested clauses; found {nested_total}"})
    if esr_standards != {"MM.5", "MM.6", "MM.41"}:
        errors.append({"code": "ESR_SET", "values": sorted(esr_standards)})
    if len(payload.documents) != 75:
        errors.append({"code": "DOCUMENT_COUNT", "message": f"Expected 75 documents; found {len(payload.documents)}"})

    doc_eids = [row.get("evidence_id") for row in payload.documents]
    if len(set(doc_eids)) != len(doc_eids):
        errors.append({"code": "DOCUMENT_EVIDENCE_ID_DUPLICATE"})

    code_counts = Counter(row.get("document_code") for row in payload.documents)
    duplicate_codes = sorted(code for code, count in code_counts.items() if count > 1)
    if duplicate_codes:
        warnings.append({"code": "DOCUMENT_CODE_DUPLICATE", "values": duplicate_codes})

    return ImportValidationResult(
        valid=not errors,
        totals={
            "measurable_elements": len(payload.me_registry),
            "nested_clauses": nested_total,
            "documents": len(payload.documents),
        },
        errors=errors,
        warnings=warnings,
    )
