"""Signed recovery assertion contract (PMP-01A.3 §2 / A.3.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID

from app.domain.recovery import RecoveryError


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

POLICY_VERSION = "manual-recovery-a3-v1"
SCHEMA_VERSION = "1"
ASSERTION_TTL_HOURS = 24


class AssertionDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ReviewerRole(StrEnum):
    PRIMARY = "primary_reviewer"
    SECOND = "second_reviewer"


@dataclass(frozen=True)
class SignedAssertion:
    assertion_id: UUID
    case_id: UUID
    operation_key: str
    policy_version: str
    evidence_reference_hash: str
    asserted_supabase_user_id: UUID
    asserted_legacy_user_id: str
    reviewer_id: UUID
    reviewer_role: ReviewerRole
    decision: AssertionDecision
    rationale_code: str
    created_at: datetime
    expires_at: datetime
    signature: str
    revoked_at: datetime | None = None
    schema_version: str = SCHEMA_VERSION

    def is_expired(self, now: datetime) -> bool:
        return _as_utc(now) >= _as_utc(self.expires_at)

    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_valid_for_quorum(self, now: datetime) -> bool:
        return (
            self.decision == AssertionDecision.APPROVE
            and not self.is_revoked()
            and not self.is_expired(now)
            and bool(self.signature)
        )


def normalize_decision(value: str) -> AssertionDecision:
    raw = value.strip().casefold()
    if raw in {"approve", "approved"}:
        return AssertionDecision.APPROVE
    if raw in {"reject", "rejected"}:
        return AssertionDecision.REJECT
    raise RecoveryError("invalid_decision", "decision must be approve or reject")
