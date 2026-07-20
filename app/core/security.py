from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import Settings, get_settings


bearer = HTTPBearer(auto_error=False)


def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "auth_required", "message": "Authentication required"})
    if not settings.supabase_jwt_secret:
        raise HTTPException(status_code=503, detail={"code": "auth_not_configured", "message": "Supabase authentication is not configured"})
    try:
        options = {"verify_aud": bool(settings.supabase_jwt_audience)}
        payload = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience or None,
            issuer=settings.supabase_jwt_issuer or None,
            options=options,
        )
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "invalid_token", "message": "Invalid access token"}) from exc
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "invalid_token", "message": "Token has no user subject"})
    try:
        return str(UUID(str(user_id)))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "Token subject is not a valid user UUID"},
        ) from exc


def get_current_user_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    if credentials is None or not settings.supabase_jwt_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "auth_required", "message": "Authentication required"})
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience or None,
            issuer=settings.supabase_jwt_issuer or None,
            options={"verify_aud": bool(settings.supabase_jwt_audience)},
        )
        subject = claims.get("sub")
        if not subject:
            raise ValueError("missing subject")
        claims["sub"] = str(UUID(str(subject)))
        return claims
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "invalid_token", "message": "Invalid access token"}) from exc


def _extract_roles(claims: dict) -> set[str]:
    """Collect privileged roles from trusted JWT claim sources only.

    Trusted sources:
    - top-level token claims (existing contract: ``role`` / ``roles``)
    - ``app_metadata`` (admin-controlled)

    ``user_metadata`` is intentionally ignored — clients can mutate it.
    """
    roles: set[str] = set()
    app_metadata = claims.get("app_metadata") or {}
    for source in (claims, app_metadata):
        if not isinstance(source, dict):
            continue
        role = source.get("role")
        if isinstance(role, str) and role:
            roles.add(role)
        role_list = source.get("roles")
        if isinstance(role_list, list):
            roles.update(str(r) for r in role_list if r)
    return roles


def get_current_recovery_reviewer(
    claims: Annotated[dict, Depends(get_current_user_claims)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UUID:
    """Reviewer identity is derived only from verified JWT + trusted role claims."""
    roles = _extract_roles(claims)
    if settings.recovery_reviewer_role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "reviewer_role_required",
                "message": "Recovery reviewer role is required",
            },
        )
    return UUID(str(claims["sub"]))
