from __future__ import annotations
from fastapi import HTTPException
from app.core.security import Principal

def require_site_access(principal: Principal, site_code: str) -> None:
    if "SystemAdmin" in principal.roles:
        return
    if site_code not in principal.site_codes:
        raise HTTPException(status_code=403, detail="Cross-site access denied")

def scoped_evidence_prefix(site_code: str, request_id: str) -> str:
    safe_site = "".join(c for c in site_code.upper() if c.isalnum() or c in "-_")
    safe_request = "".join(c for c in request_id if c.isalnum() or c in "-_")
    if not safe_site or not safe_request:
        raise ValueError("Invalid site or request identifier")
    return f"sites/{safe_site}/evidence/{safe_request}"
