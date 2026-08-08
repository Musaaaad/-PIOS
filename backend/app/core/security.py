from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from typing import Annotated, Any

import jwt
from jwt import PyJWK, PyJWKClient
from jwt.exceptions import PyJWKClientError
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


# Roles Keycloak issues to every account as housekeeping. They are not PIOS
# roles and grant nothing here, but they arrive in the same `roles` claim as a
# real assignment. Counting them defeated deny-by-default: a user with no PIOS
# role still presented three roles and was admitted.
KEYCLOAK_RESERVED_ROLES = frozenset({"offline_access", "uma_authorization", "create-realm"})
KEYCLOAK_RESERVED_PREFIX = "default-roles-"


def _application_roles(roles: frozenset[str]) -> frozenset[str]:
    return frozenset(
        r for r in roles
        if r not in KEYCLOAK_RESERVED_ROLES and not r.startswith(KEYCLOAK_RESERVED_PREFIX)
    )


def _claim_values(value: Any) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str):
        return frozenset(x.strip() for x in value.replace(";", ",").split(",") if x.strip())
    if isinstance(value, (list, tuple, set)):
        return frozenset(str(x).strip() for x in value if str(x).strip())
    return frozenset({str(value)})


class ProviderUnavailable(Exception):
    """The identity provider is unusable - a SERVER fault, not a bad token.

    Two situations reach here: this service has no issuer/audience/JWKS
    configured, and the provider's key set could not be fetched. Both were
    previously reported as 401 "Invalid OIDC token", which blames the user's
    session for an operator or infrastructure problem and sends the browser
    into a re-authentication loop that can never succeed - signing in again
    cannot supply a missing environment variable or wake a sleeping provider.
    """


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    """One client per URL, reused.

    A fresh PyJWKClient per request re-fetched the key set on EVERY call and
    threw its cache away, so each request depended on the provider being
    reachable right then. On a platform whose instances sleep, that turns a
    slow identity provider into an authentication failure.
    """
    return PyJWKClient(url, cache_keys=True, lifespan=300)


def decode_oidc_token(token: str, settings: Settings) -> dict[str, Any]:
    if not settings.oidc_issuer or not settings.oidc_audience:
        raise ProviderUnavailable("identity provider is not configured on this service")

    key = None
    if settings.oidc_jwks_json:
        jwks = json.loads(settings.oidc_jwks_json)
        header = jwt.get_unverified_header(token)
        candidates = [x for x in jwks.get("keys", []) if x.get("kid") == header.get("kid")]
        if not candidates:
            raise ValueError("No matching OIDC signing key")
        key = PyJWK.from_dict(candidates[0]).key
    elif settings.oidc_jwks_url:
        try:
            key = _jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token).key
        except PyJWKClientError as exc:
            # Could not obtain the key set. The token may be perfectly valid;
            # we simply cannot check it right now.
            raise ProviderUnavailable(f"identity provider key set unavailable: {exc}") from exc
    else:
        raise ProviderUnavailable("identity provider key source is not configured on this service")

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
    except ProviderUnavailable as exc:
        # Server-side fault. Never 401: re-authenticating cannot fix it.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid OIDC token: {exc}") from exc

    user_id = str(claims.get(settings.oidc_user_id_claim) or "")
    # The token authenticated. Whether it authorizes anything is a separate
    # question, and its answer is 403 - never 401.
    roles = _application_roles(_claim_values(claims.get(settings.oidc_roles_claim)))
    if not user_id:
        raise HTTPException(status_code=401, detail="OIDC token carries no user id")
    if not roles:
        raise HTTPException(
            status_code=403,
            detail="Authenticated, but no PIOS role is assigned to this account",
        )
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
