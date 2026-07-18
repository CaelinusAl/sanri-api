"""Durable Signed Assertion Store (PMP-01A.3.2).

Authority rules:
- Only this store (Recovery Service path) may create server-signed assertions.
- Client-supplied signatures / reviewer authority fields are rejected.
- Revocation is append-only; records are never deleted.
- Expired or revoked approvals never count toward quorum.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.assertion_signing import (
    as_utc,
    canonical_assertion_payload,
    sign_canonical_payload,
    verify_assertion_signature,
)
from app.domain.assertion import (
    ASSERTION_TTL_HOURS,
    POLICY_VERSION,
    SCHEMA_VERSION,
    AssertionDecision,
    ReviewerRole,
    SignedAssertion,
    normalize_decision,
)
from app.domain.recovery import RecoveryError
from app.models.recovery_assertion import V1RecoveryAssertion


class DurableSignedAssertionStore:
    def __init__(self, session: Session, *, signing_secret: str):
        self.session = session
        self.signing_secret = signing_secret

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _to_domain(self, row: V1RecoveryAssertion) -> SignedAssertion:
        return SignedAssertion(
            assertion_id=row.assertion_id,
            case_id=row.case_id,
            operation_key=row.operation_key,
            policy_version=row.policy_version,
            evidence_reference_hash=row.evidence_reference_hash,
            asserted_supabase_user_id=row.asserted_supabase_user_id,
            asserted_legacy_user_id=row.asserted_legacy_user_id,
            reviewer_id=row.reviewer_id,
            reviewer_role=ReviewerRole(row.reviewer_role),
            decision=AssertionDecision(row.decision),
            rationale_code=row.rationale_code,
            created_at=as_utc(row.created_at),
            expires_at=as_utc(row.expires_at),
            signature=row.signature,
            revoked_at=as_utc(row.revoked_at) if row.revoked_at is not None else None,
            schema_version=row.schema_version,
        )

    def get(self, assertion_id: UUID) -> SignedAssertion:
        row = self.session.get(V1RecoveryAssertion, assertion_id)
        if row is None:
            raise RecoveryError("assertion_not_found", "Signed assertion not found")
        return self._to_domain(row)

    def get_by_operation_key(self, operation_key: str) -> SignedAssertion | None:
        row = self.session.scalar(
            select(V1RecoveryAssertion).where(V1RecoveryAssertion.operation_key == operation_key)
        )
        return self._to_domain(row) if row else None

    def list_for_case(self, case_id: UUID) -> list[SignedAssertion]:
        rows = self.session.scalars(
            select(V1RecoveryAssertion)
            .where(V1RecoveryAssertion.case_id == case_id)
            .order_by(V1RecoveryAssertion.created_at.asc())
        ).all()
        return [self._to_domain(r) for r in rows]

    def verify(self, assertion: SignedAssertion) -> bool:
        return verify_assertion_signature(assertion, self.signing_secret)

    def list_valid_approvals(
        self,
        *,
        case_id: UUID,
        evidence_reference_hash: str,
        now: datetime | None = None,
    ) -> list[SignedAssertion]:
        """Quorum candidates: non-expired, non-revoked, signature-valid approvals.

        Contract clarification: each assertion has its own operation_key for
        idempotency; quorum is evaluated on case_id + evidence_reference_hash.
        """
        clock = now or self._now()
        out: list[SignedAssertion] = []
        for assertion in self.list_for_case(case_id):
            if assertion.evidence_reference_hash != evidence_reference_hash:
                continue
            if not assertion.is_valid_for_quorum(clock):
                continue
            if not self.verify(assertion):
                continue
            out.append(assertion)
        return out

    def has_approval_quorum(
        self,
        *,
        case_id: UUID,
        evidence_reference_hash: str,
        now: datetime | None = None,
    ) -> bool:
        approvals = self.list_valid_approvals(
            case_id=case_id,
            evidence_reference_hash=evidence_reference_hash,
            now=now,
        )
        reviewers = {a.reviewer_id for a in approvals}
        return len(approvals) >= 2 and len(reviewers) >= 2

    def _assign_reviewer_role(self, case_id: UUID, reviewer_id: UUID) -> ReviewerRole:
        prior = [a for a in self.list_for_case(case_id) if not a.is_revoked()]
        if any(a.reviewer_id == reviewer_id for a in prior):
            raise RecoveryError(
                "four_eyes_conflict",
                "Same reviewer cannot submit a second assertion on this case",
            )
        approvals = [a for a in prior if a.decision == AssertionDecision.APPROVE]
        if any(a.reviewer_role == ReviewerRole.PRIMARY for a in approvals):
            return ReviewerRole.SECOND
        return ReviewerRole.PRIMARY

    def create(
        self,
        *,
        case_id: UUID,
        operation_key: str,
        evidence_reference_hash: str,
        asserted_supabase_user_id: UUID,
        asserted_legacy_user_id: str,
        reviewer_id: UUID,
        decision: str,
        rationale_code: str,
        client_signature: str | None = None,
        client_reviewer_id: UUID | None = None,
        client_reviewer_role: str | None = None,
        policy_version: str | None = None,
    ) -> tuple[SignedAssertion, bool]:
        if client_signature is not None:
            raise RecoveryError(
                "client_assertion_forbidden",
                "Client-supplied assertion signatures are forbidden",
            )
        if client_reviewer_id is not None or client_reviewer_role is not None:
            raise RecoveryError(
                "client_assertion_forbidden",
                "Client-supplied reviewer authority is forbidden",
            )
        if policy_version is not None and policy_version != POLICY_VERSION:
            raise RecoveryError(
                "policy_version_mismatch",
                "Only the locked recovery policy_version may be applied",
            )
        if not rationale_code or len(rationale_code) > 64:
            raise RecoveryError("invalid_rationale_code", "rationale_code is required")

        existing = self.get_by_operation_key(operation_key)
        if existing is not None:
            return existing, True

        normalized = normalize_decision(decision)
        role = self._assign_reviewer_role(case_id, reviewer_id)
        assertion_id = uuid4()
        created_at = self._now()
        expires_at = created_at + timedelta(hours=ASSERTION_TTL_HOURS)
        canonical = canonical_assertion_payload(
            assertion_id=assertion_id,
            case_id=case_id,
            operation_key=operation_key,
            policy_version=POLICY_VERSION,
            evidence_reference_hash=evidence_reference_hash,
            asserted_supabase_user_id=asserted_supabase_user_id,
            asserted_legacy_user_id=asserted_legacy_user_id,
            reviewer_id=reviewer_id,
            reviewer_role=str(role),
            decision=str(normalized),
            rationale_code=rationale_code,
            created_at=created_at,
            expires_at=expires_at,
            schema_version=SCHEMA_VERSION,
        )
        signature = sign_canonical_payload(canonical, self.signing_secret)

        row = V1RecoveryAssertion(
            assertion_id=assertion_id,
            case_id=case_id,
            operation_key=operation_key,
            policy_version=POLICY_VERSION,
            schema_version=SCHEMA_VERSION,
            evidence_reference_hash=evidence_reference_hash,
            asserted_supabase_user_id=asserted_supabase_user_id,
            asserted_legacy_user_id=asserted_legacy_user_id,
            reviewer_id=reviewer_id,
            reviewer_role=str(role),
            decision=str(normalized),
            rationale_code=rationale_code,
            signature=signature,
            created_at=created_at,
            expires_at=expires_at,
            revoked_at=None,
        )
        self.session.add(row)
        self.session.flush()
        return self._to_domain(row), False

    def revoke(self, assertion_id: UUID, *, now: datetime | None = None) -> SignedAssertion:
        row = self.session.get(V1RecoveryAssertion, assertion_id)
        if row is None:
            raise RecoveryError("assertion_not_found", "Signed assertion not found")
        if row.revoked_at is not None:
            return self._to_domain(row)
        row.revoked_at = now or self._now()
        self.session.flush()
        return self._to_domain(row)

    def delete(self, assertion_id: UUID) -> None:
        raise RecoveryError(
            "assertion_immutable",
            "Signed assertions cannot be deleted; revoke append-only",
        )

    def mutate_policy_version(self, assertion_id: UUID, policy_version: str) -> None:
        raise RecoveryError(
            "assertion_immutable",
            "policy_version is immutable on a signed assertion",
        )
