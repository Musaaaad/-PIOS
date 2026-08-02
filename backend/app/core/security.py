from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Annotated, Any

import jwt
from jwt import PyJWK, PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: str
    roles: frozenset[str]
    email: str | None = None
    display_name: str | None = None
    site_codes: frozenset[str] = frozenset()
    auth_source: str = "dev"


def _claim_values(value: Any) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str):
        return frozenset(x.strip() for x in value.replace(";", ",").split(",") if x.strip())
    if isinstance(value, (list, tuple, set)):
        return frozenset(str(x).strip() for x in value if str(x).strip())
    return frozenset({str(value)})


def decode_oidc_token(token: str, settings: Settings) -> dict[str, Any]:
    if not settings.oidc_issuer or not settings.oidc_audience:
        raise ValueError("OIDC issuer and audience must be configured")

    key = None
    if settings.oidc_jwks_json:
        jwks = json.loads(settings.oidc_jwks_json)
        header = jwt.get_unverified_header(token)
        candidates = [x for x in jwks.get("keys", []) if x.get("kid") == header.get("kid")]
        if not candidates:
            raise ValueError("No matching OIDC signing key")
        key = PyJWK.from_dict(candidates[0]).key
    elif settings.oidc_jwks_url:
        key = PyJWKClient(settings.oidc_jwks_url).get_signing_key_from_jwt(token).key
    else:
        raise ValueError("OIDC JWKS URL or inline JWKS must be configured")

    return jwt.decode(
        token,
        key=key,
        algorithms=settings.oidc_algorithm_list,
        audience=settings.oidc_audience,
        issuer=settings.oidc_issuer,
        options={"require": ["exp", settings.oidc_user_id_claim]},
    )


def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    settings = get_settings()
    if credentials is None:
        if settings.env == "test":
            return Principal("test-user", frozenset({"SystemAdmin"}), auth_source="test")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")

    token = credentials.credentials
    if settings.allow_dev_tokens and settings.env != "production" and token.startswith("dev:"):
        parts = token.split(":", 2)
        if len(parts) != 3:
            raise HTTPException(status_code=401, detail="Invalid development token")
        user_id, roles_text = parts[1], parts[2]
        roles = _claim_values(roles_text)
        return Principal(user_id=user_id, roles=roles, auth_source="dev")

    if settings.auth_mode != "oidc":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC authentication is not enabled")

    try:
        claims = decode_oidc_token(token, settings)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid OIDC token: {exc}") from exc

    user_id = str(claims.get(settings.oidc_user_id_claim) or "")
    roles = _claim_values(claims.get(settings.oidc_roles_claim))
    if not user_id or not roles:
        raise HTTPException(status_code=403, detail="OIDC token does not contain a user id and mapped roles")
    return Principal(
        user_id=user_id,
        roles=roles,
        email=claims.get(settings.oidc_email_claim),
        display_name=claims.get(settings.oidc_name_claim),
        site_codes=_claim_values(claims.get(settings.oidc_site_claim)),
        auth_source="oidc",
    )


def require_roles(*required: str):
    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if not principal.roles.intersection(required):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return principal
    return dependency
