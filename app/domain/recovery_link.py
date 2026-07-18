"""Recovery link lifecycle contract (PMP-01A.3.4).

Secrets are stored hashed only. Raw tokens are never persisted and are
returned once at create time.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.domain.recovery import RecoveryError

LINK_TTL_HOURS = 24
TOKEN_BYTES = 32


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def generate_recovery_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_recovery_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RecoveryLink:
    link_id: UUID
    case_id: UUID
    operation_key: str
    token_hash: str
    evidence_reference_hash: str
    created_by: UUID
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    revoked_by: UUID | None = None
    revoke_reason: str | None = None
    used_at: datetime | None = None

    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_used(self) -> bool:
        return self.used_at is not None

    def is_expired(self, now: datetime) -> bool:
        return _as_utc(now) >= _as_utc(self.expires_at)

    def is_active(self, now: datetime) -> bool:
        return not self.is_revoked() and not self.is_used() and not self.is_expired(now)


def require_revoke_reason(reason: str | None) -> str:
    cleaned = (reason or "").strip()
    if not cleaned:
        raise RecoveryError("revoke_reason_required", "Recovery link revoke requires a reason")
    if len(cleaned) > 2000:
        raise RecoveryError("revoke_reason_required", "Recovery link revoke reason is too long")
    return cleaned
