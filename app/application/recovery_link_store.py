"""Durable Recovery Link Store (PMP-01A.3.4).

Authority rules:
- Raw tokens are never persisted.
- Revocation is append-only (revoked_at / revoked_by / reason).
- Expired or used links cannot be reactivated.
- At most one active (non-revoked, non-used) link per case.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.assertion_signing import as_utc
from app.domain.recovery import RecoveryError
from app.domain.recovery_link import (
    LINK_TTL_HOURS,
    RecoveryLink,
    generate_recovery_token,
    hash_recovery_token,
    require_revoke_reason,
)
from app.models.recovery_link import V1RecoveryLink


class DurableRecoveryLinkStore:
    def __init__(self, session: Session):
        self.session = session

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _to_domain(self, row: V1RecoveryLink) -> RecoveryLink:
        return RecoveryLink(
            link_id=row.link_id,
            case_id=row.case_id,
            operation_key=row.operation_key,
            token_hash=row.token_hash,
            evidence_reference_hash=row.evidence_reference_hash,
            created_by=row.created_by,
            created_at=as_utc(row.created_at),
            expires_at=as_utc(row.expires_at),
            revoked_at=as_utc(row.revoked_at) if row.revoked_at is not None else None,
            revoked_by=row.revoked_by,
            revoke_reason=row.revoke_reason,
            used_at=as_utc(row.used_at) if row.used_at is not None else None,
        )

    def get(self, link_id: UUID) -> RecoveryLink:
        row = self.session.get(V1RecoveryLink, link_id)
        if row is None:
            raise RecoveryError("link_not_found", "Recovery link not found")
        return self._to_domain(row)

    def get_by_operation_key(self, operation_key: str) -> RecoveryLink | None:
        row = self.session.scalar(
            select(V1RecoveryLink).where(V1RecoveryLink.operation_key == operation_key)
        )
        return self._to_domain(row) if row else None

    def list_for_case(self, case_id: UUID) -> list[RecoveryLink]:
        rows = self.session.scalars(
            select(V1RecoveryLink)
            .where(V1RecoveryLink.case_id == case_id)
            .order_by(V1RecoveryLink.created_at.asc())
        ).all()
        return [self._to_domain(r) for r in rows]

    def get_active_for_case(
        self, case_id: UUID, *, now: datetime | None = None
    ) -> RecoveryLink | None:
        clock = now or self._now()
        for link in self.list_for_case(case_id):
            if link.is_active(clock):
                return link
        return None

    def create(
        self,
        *,
        case_id: UUID,
        operation_key: str,
        evidence_reference_hash: str,
        created_by: UUID,
        raw_token: str | None = None,
    ) -> tuple[RecoveryLink, str | None, bool]:
        """Create a recovery link. Returns (link, raw_token|None, replayed).

        On idempotent replay, raw_token is always None.
        """
        existing = self.get_by_operation_key(operation_key)
        if existing is not None:
            return existing, None, True

        active = self.get_active_for_case(case_id)
        if active is not None:
            raise RecoveryError(
                "active_link_exists",
                "Only one active recovery link is allowed per case",
            )

        token = raw_token or generate_recovery_token()
        token_hash = hash_recovery_token(token)
        created_at = self._now()
        row = V1RecoveryLink(
            link_id=uuid4(),
            case_id=case_id,
            operation_key=operation_key,
            token_hash=token_hash,
            evidence_reference_hash=evidence_reference_hash,
            created_by=created_by,
            created_at=created_at,
            expires_at=created_at + timedelta(hours=LINK_TTL_HOURS),
            revoked_at=None,
            revoked_by=None,
            revoke_reason=None,
            used_at=None,
        )
        self.session.add(row)
        self.session.flush()
        return self._to_domain(row), token, False

    def revoke(
        self,
        link_id: UUID,
        *,
        revoked_by: UUID,
        reason: str,
        now: datetime | None = None,
    ) -> tuple[RecoveryLink, bool]:
        """Append-only revoke. Returns (link, already_revoked)."""
        cleaned = require_revoke_reason(reason)
        row = self.session.get(V1RecoveryLink, link_id)
        if row is None:
            raise RecoveryError("link_not_found", "Recovery link not found")
        if row.revoked_at is not None:
            return self._to_domain(row), True
        if row.used_at is not None:
            # Used links stay used; revoke still stamps metadata but never reactivates.
            pass
        row.revoked_at = now or self._now()
        row.revoked_by = revoked_by
        row.revoke_reason = cleaned
        self.session.flush()
        return self._to_domain(row), False

    def mark_used(self, link_id: UUID, *, now: datetime | None = None) -> RecoveryLink:
        row = self.session.get(V1RecoveryLink, link_id)
        if row is None:
            raise RecoveryError("link_not_found", "Recovery link not found")
        if row.used_at is not None:
            return self._to_domain(row)
        if row.revoked_at is not None:
            raise RecoveryError("link_not_active", "Revoked recovery links cannot be used")
        clock = now or self._now()
        if as_utc(clock) >= as_utc(row.expires_at):
            raise RecoveryError("link_expired", "Expired recovery links cannot be used")
        row.used_at = clock
        self.session.flush()
        return self._to_domain(row)

    def reactivate(self, link_id: UUID) -> None:
        raise RecoveryError(
            "link_immutable",
            "Expired, used, or revoked recovery links cannot be reactivated",
        )
