"""Guards for legacy endpoints that cannot establish canonical identity."""

from fastapi import HTTPException, status


def reject_unsafe_legacy_identity() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "canonical_identity_required",
            "message": "A verified Supabase identity is required for this resource.",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def reject_legacy_auth() -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "legacy_auth_disabled",
            "message": "Use Supabase Auth to create a canonical SANRI identity.",
        },
    )
