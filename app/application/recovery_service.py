"""Recovery mutations with four-eyes (A.3.3), links (A.3.4), durable cases/audit (A.3.6/A.3.7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.application.assertion_store import DurableSignedAssertionStore
from app.application.recovery_audit_store import (
    DurableAuditWriter,
    entity_ref_from_detail,
    sanitize_audit_detail,
)
from app.application.recovery_link_store import DurableRecoveryLinkStore
from app.domain.assertion import AssertionDecision, SignedAssertion
from app.domain.recovery import (
    RecoveryCaseState,
    RecoveryError,
    TERMINAL_STATES,
    assert_transition_allowed,
)
from app.domain.recovery_link import RecoveryLink

CASE_TTL = timedelta(hours=72)


@dataclass
class AssertionRecord:
    assertion_id: UUID
    case_id: UUID
    reviewer_id: UUID
    decision: str
    rationale: str
    operation_key: str
    created_at: datetime
    revoked_at: datetime | None = None


@dataclass
class AuditRecord:
    audit_id: UUID
    case_id: UUID
    actor_id: UUID
    action: str
    from_state: str | None
    to_state: str | None
    operation_key: str
    created_at: datetime
    detail: dict
    entity_ref: str | None = None


@dataclass
class RecoveryCaseRecord:
    case_id: UUID
    state: RecoveryCaseState
    subject_user_id: UUID
    claimed_legacy_identity_ref: str
    created_by: UUID
    evidence_hash: str | None = None
    evidence_type: str | None = None
    notes: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    assertions: list[AssertionRecord] = field(default_factory=list)
    state_version: int = 0


class AuditWriter(Protocol):
    def write(self, record: AuditRecord) -> None: ...


class InMemoryAuditWriter:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.records: list[AuditRecord] = []

    def write(self, record: AuditRecord) -> None:
        if self.fail:
            raise RuntimeError("audit_write_failed")
        self.records.append(record)


class RecoveryStore:
    """In-process case store (A.3.1 harness). Durable path is DurableRecoveryCaseStore."""

    def __init__(self) -> None:
        self.cases: dict[UUID, RecoveryCaseRecord] = {}
        self.operations: dict[str, UUID] = {}

    def get(self, case_id: UUID) -> RecoveryCaseRecord | None:
        return self.cases.get(case_id)

    def get_case_id_for_operation(self, operation_key: str) -> UUID | None:
        return self.operations.get(operation_key)

    def list_open_for_identity(
        self,
        *,
        subject_user_id: UUID,
        claimed_legacy_identity_ref: str,
    ) -> list[RecoveryCaseRecord]:
        out: list[RecoveryCaseRecord] = []
        for case in self.cases.values():
            if case.state in TERMINAL_STATES:
                continue
            if (
                case.subject_user_id == subject_user_id
                or case.claimed_legacy_identity_ref == claimed_legacy_identity_ref
            ):
                out.append(case)
        return out

    def bind_operation(self, operation_key: str, case_id: UUID) -> None:
        existing = self.operations.get(operation_key)
        if existing is not None and existing != case_id:
            raise RecoveryError(
                "operation_key_conflict",
                "operation_key already bound to a different recovery case",
            )
        self.operations[operation_key] = case_id

    def create(self, case: RecoveryCaseRecord, *, operation_key: str) -> RecoveryCaseRecord:
        if self.list_open_for_identity(
            subject_user_id=case.subject_user_id,
            claimed_legacy_identity_ref=case.claimed_legacy_identity_ref,
        ):
            raise RecoveryError(
                "duplicate_open_case",
                "At most one non-terminal recovery case per subject or legacy identity",
            )
        case.state_version = 0
        self.cases[case.case_id] = case
        self.bind_operation(operation_key, case.case_id)
        return case

    def save(
        self,
        case: RecoveryCaseRecord,
        *,
        expected_version: int,
        operation_key: str | None = None,
    ) -> RecoveryCaseRecord:
        current = self.cases.get(case.case_id)
        if current is None:
            raise RecoveryError("case_not_found", "Recovery case not found")
        if current.state_version != expected_version:
            raise RecoveryError(
                "conflict_state",
                "Concurrent case mutation rejected; reload and retry",
            )
        if current.state in TERMINAL_STATES and case.state not in TERMINAL_STATES:
            raise RecoveryError(
                "terminal_case_immutable",
                "Terminal recovery cases cannot be mutated",
            )
        case.state_version = expected_version + 1
        self.cases[case.case_id] = case
        if operation_key is not None:
            self.bind_operation(operation_key, case.case_id)
        return case


def _rationale_to_code(rationale: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in rationale.strip())
    cleaned = cleaned.strip("_").upper()[:64]
    return cleaned or "UNSPECIFIED"


def _signed_to_record(assertion: SignedAssertion) -> AssertionRecord:
    return AssertionRecord(
        assertion_id=assertion.assertion_id,
        case_id=assertion.case_id,
        reviewer_id=assertion.reviewer_id,
        decision="APPROVE" if assertion.decision == AssertionDecision.APPROVE else "REJECT",
        rationale=assertion.rationale_code,
        operation_key=assertion.operation_key,
        created_at=assertion.created_at,
        revoked_at=assertion.revoked_at,
    )


class RecoveryService:
    """Four-eyes workflow + recovery link lifecycle via durable stores."""

    def __init__(
        self,
        store: RecoveryStore,
        audit: AuditWriter | None = None,
        *,
        assertion_store: DurableSignedAssertionStore | None = None,
        link_store: DurableRecoveryLinkStore | None = None,
        db_session: Session | None = None,
    ):
        self.store = store
        self.assertion_store = assertion_store
        self.link_store = link_store
        self.db_session = db_session if db_session is not None else (
            assertion_store.session if assertion_store is not None else (
                link_store.session if link_store is not None else None
            )
        )
        # Runtime path: durable audit when a DB session exists.
        # InMemoryAuditWriter is only for explicitly injected test/legacy harnesses.
        if audit is not None:
            self.audit = audit
        elif self.db_session is not None:
            try:
                self.audit = DurableAuditWriter(self.db_session)
            except Exception as exc:
                raise RecoveryError(
                    "audit_unavailable",
                    "Durable audit ledger unavailable; refusing recovery mutations",
                ) from exc
        else:
            raise RecoveryError(
                "audit_unavailable",
                "Durable audit requires a database session; "
                "inject InMemoryAuditWriter only for explicit test harnesses",
            )

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _require_assertion_store(self) -> DurableSignedAssertionStore:
        if self.assertion_store is None:
            raise RecoveryError(
                "assertion_store_required",
                "Four-eyes workflow requires the durable signed assertion store",
            )
        return self.assertion_store

    def _require_link_store(self) -> DurableRecoveryLinkStore:
        if self.link_store is None:
            raise RecoveryError(
                "link_store_required",
                "Recovery link lifecycle requires the durable recovery link store",
            )
        return self.link_store

    def _commit_tx(self) -> None:
        if self.db_session is not None:
            self.db_session.commit()

    def _rollback_tx(self) -> None:
        if self.db_session is not None:
            self.db_session.rollback()

    def _sync_case_assertions(self, case: RecoveryCaseRecord) -> None:
        assertion_store = self.assertion_store
        if assertion_store is None:
            return
        case.assertions = [_signed_to_record(a) for a in assertion_store.list_for_case(case.case_id)]

    def _persist(
        self,
        case: RecoveryCaseRecord,
        *,
        expected_version: int,
        operation_key: str | None = None,
    ) -> None:
        self.store.save(case, expected_version=expected_version, operation_key=operation_key)

    def _recompute_review_state(
        self,
        case: RecoveryCaseRecord,
        *,
        actor_id: UUID,
        operation_key: str,
        action: str,
    ) -> None:
        """Derive pre-link review state from store quorum (source of truth)."""
        assertion_store = self._require_assertion_store()
        if not case.evidence_hash:
            return

        if case.state not in {
            RecoveryCaseState.READY_FOR_REVIEW,
            RecoveryCaseState.AWAITING_SECOND_APPROVAL,
        }:
            # APPROVED+ quorum loss is enforced at future link-create time; state
            # machine does not reopen APPROVED cases here.
            return

        if assertion_store.has_approval_quorum(
            case_id=case.case_id,
            evidence_reference_hash=case.evidence_hash,
        ):
            self._transition(
                case,
                RecoveryCaseState.APPROVED,
                actor_id=actor_id,
                operation_key=operation_key,
                action=action,
            )
            return

        valid = assertion_store.list_valid_approvals(
            case_id=case.case_id,
            evidence_reference_hash=case.evidence_hash,
        )
        target = (
            RecoveryCaseState.AWAITING_SECOND_APPROVAL
            if valid
            else RecoveryCaseState.READY_FOR_REVIEW
        )
        if case.state != target:
            self._transition(
                case,
                target,
                actor_id=actor_id,
                operation_key=operation_key,
                action=action,
            )

    def _expire_if_needed(self, case: RecoveryCaseRecord) -> bool:
        if case.state in TERMINAL_STATES:
            return False
        if case.expires_at and self._now() >= case.expires_at:
            prev = case.state
            case.state = RecoveryCaseState.EXPIRED
            case.updated_at = self._now()
            try:
                self._audit(
                    case_id=case.case_id,
                    actor_id=case.created_by,
                    action="expire",
                    from_state=prev,
                    to_state=case.state,
                    operation_key=f"system-expire-{case.case_id}",
                )
            except Exception:
                pass
            return True
        return False

    def _audit(
        self,
        *,
        case_id: UUID,
        actor_id: UUID,
        action: str,
        from_state: RecoveryCaseState | str | None,
        to_state: RecoveryCaseState | str | None,
        operation_key: str,
        detail: dict | None = None,
    ) -> None:
        safe_detail = sanitize_audit_detail(detail)
        self.audit.write(
            AuditRecord(
                audit_id=uuid4(),
                case_id=case_id,
                actor_id=actor_id,
                action=action,
                from_state=str(from_state) if from_state is not None else None,
                to_state=str(to_state) if to_state is not None else None,
                operation_key=operation_key,
                created_at=self._now(),
                detail=safe_detail,
                entity_ref=entity_ref_from_detail(safe_detail),
            )
        )

    def _transition(
        self,
        case: RecoveryCaseRecord,
        target: RecoveryCaseState,
        *,
        actor_id: UUID,
        operation_key: str,
        action: str,
        detail: dict | None = None,
    ) -> None:
        assert_transition_allowed(case.state, target)
        prev = case.state
        case.state = target
        case.updated_at = self._now()
        self._audit(
            case_id=case.case_id,
            actor_id=actor_id,
            action=action,
            from_state=prev,
            to_state=target,
            operation_key=operation_key,
            detail=detail,
        )

    def _rollback_audit_failure(self) -> RecoveryError:
        return RecoveryError("audit_failed", "Mutation rolled back because audit write failed")

    def _ensure_no_duplicate_open_case(
        self,
        *,
        subject_user_id: UUID,
        claimed_legacy_identity_ref: str,
    ) -> None:
        open_cases = self.store.list_open_for_identity(
            subject_user_id=subject_user_id,
            claimed_legacy_identity_ref=claimed_legacy_identity_ref,
        )
        if open_cases:
            raise RecoveryError(
                "duplicate_open_case",
                "At most one non-terminal recovery case per subject or legacy identity",
            )

    def get_case(self, case_id: UUID) -> RecoveryCaseRecord:
        case = self.store.get(case_id)
        if case is None:
            raise RecoveryError("case_not_found", "Recovery case not found")
        expected = case.state_version
        mutated = self._expire_if_needed(case)
        self._sync_case_assertions(case)
        # Expired assertions may drop quorum while still awaiting second approval.
        if (
            self.assertion_store is not None
            and case.evidence_hash
            and case.state == RecoveryCaseState.AWAITING_SECOND_APPROVAL
            and not self.assertion_store.has_approval_quorum(
                case_id=case.case_id,
                evidence_reference_hash=case.evidence_hash,
            )
        ):
            valid = self.assertion_store.list_valid_approvals(
                case_id=case.case_id,
                evidence_reference_hash=case.evidence_hash,
            )
            if not valid:
                try:
                    self._recompute_review_state(
                        case,
                        actor_id=case.created_by,
                        operation_key=f"system-quorum-recheck-{case.case_id}",
                        action="quorum_recheck",
                    )
                    mutated = True
                except RecoveryError:
                    pass
        if mutated:
            try:
                self._persist(case, expected_version=expected)
                self._commit_tx()
            except RecoveryError:
                self._rollback_tx()
                refreshed = self.store.get(case_id)
                if refreshed is not None:
                    case = refreshed
                    self._sync_case_assertions(case)
        return case

    def create_case(
        self,
        *,
        reviewer_id: UUID,
        operation_key: str,
        subject_user_id: UUID,
        claimed_legacy_identity_ref: str,
        notes: str | None = None,
    ) -> tuple[RecoveryCaseRecord, bool]:
        existing = self.store.get_case_id_for_operation(operation_key)
        if existing is not None:
            return self.get_case(existing), True

        self._ensure_no_duplicate_open_case(
            subject_user_id=subject_user_id,
            claimed_legacy_identity_ref=claimed_legacy_identity_ref,
        )

        case = RecoveryCaseRecord(
            case_id=uuid4(),
            state=RecoveryCaseState.DRAFT,
            subject_user_id=subject_user_id,
            claimed_legacy_identity_ref=claimed_legacy_identity_ref,
            created_by=reviewer_id,
            notes=notes,
            expires_at=self._now() + CASE_TTL,
        )
        try:
            self._transition(
                case,
                RecoveryCaseState.EVIDENCE_PENDING,
                actor_id=reviewer_id,
                operation_key=operation_key,
                action="create_case",
                detail={"subject_user_id": str(subject_user_id)},
            )
            self.store.create(case, operation_key=operation_key)
            self._commit_tx()
        except RecoveryError:
            self._rollback_tx()
            raise
        except Exception as exc:
            self._rollback_tx()
            raise self._rollback_audit_failure() from exc

        return case, False

    def submit_evidence(
        self,
        *,
        case_id: UUID,
        reviewer_id: UUID,
        operation_key: str,
        evidence_hash: str,
        evidence_type: str,
    ) -> tuple[RecoveryCaseRecord, bool]:
        existing = self.store.get_case_id_for_operation(operation_key)
        if existing is not None:
            return self.get_case(existing), True

        case = self.get_case(case_id)
        if case.state in TERMINAL_STATES:
            raise RecoveryError("terminal_case_immutable", "Terminal recovery cases cannot be mutated")

        expected = case.state_version
        snapshot_state = case.state
        snapshot_hash = case.evidence_hash
        snapshot_type = case.evidence_type
        snapshot_updated = case.updated_at
        evidence_changed = bool(case.evidence_hash and case.evidence_hash != evidence_hash)

        try:
            if evidence_changed and case.state in {
                RecoveryCaseState.READY_FOR_REVIEW,
                RecoveryCaseState.AWAITING_SECOND_APPROVAL,
                RecoveryCaseState.APPROVED,
            }:
                # Prior approvals become invalid for quorum via evidence hash mismatch.
                case.state = RecoveryCaseState.EVIDENCE_PENDING

            case.evidence_hash = evidence_hash
            case.evidence_type = evidence_type
            if case.state in {RecoveryCaseState.DRAFT, RecoveryCaseState.EVIDENCE_PENDING}:
                self._transition(
                    case,
                    RecoveryCaseState.READY_FOR_REVIEW,
                    actor_id=reviewer_id,
                    operation_key=operation_key,
                    action="submit_evidence",
                    detail={
                        "evidence_type": evidence_type,
                        "reason": "evidence_changed" if evidence_changed else None,
                    },
                )
            else:
                case.updated_at = self._now()
                self._audit(
                    case_id=case.case_id,
                    actor_id=reviewer_id,
                    action="submit_evidence",
                    from_state=case.state,
                    to_state=case.state,
                    operation_key=operation_key,
                    detail={"evidence_type": evidence_type},
                )
            self._persist(case, expected_version=expected, operation_key=operation_key)
            self._commit_tx()
        except RecoveryError:
            self._rollback_tx()
            case.state = snapshot_state
            case.evidence_hash = snapshot_hash
            case.evidence_type = snapshot_type
            case.updated_at = snapshot_updated
            raise
        except Exception as exc:
            self._rollback_tx()
            case.state = snapshot_state
            case.evidence_hash = snapshot_hash
            case.evidence_type = snapshot_type
            case.updated_at = snapshot_updated
            raise self._rollback_audit_failure() from exc

        self._sync_case_assertions(case)
        return case, False

    def create_assertion(
        self,
        *,
        case_id: UUID,
        reviewer_id: UUID,
        operation_key: str,
        decision: str,
        rationale: str,
    ) -> tuple[RecoveryCaseRecord, AssertionRecord, bool]:
        assertion_store = self._require_assertion_store()

        # Resume by durable operation_key (restart-safe).
        existing = assertion_store.get_by_operation_key(operation_key)
        if existing is not None:
            case = self.get_case(case_id)
            if existing.case_id != case.case_id:
                raise RecoveryError(
                    "operation_key_conflict",
                    "operation_key already bound to a different recovery case",
                )
            self._sync_case_assertions(case)
            self.store.bind_operation(operation_key, case.case_id)
            return case, _signed_to_record(existing), True

        case = self.get_case(case_id)
        if case.state in TERMINAL_STATES:
            raise RecoveryError("terminal_case_immutable", "Terminal recovery cases cannot be mutated")
        if case.state not in {
            RecoveryCaseState.READY_FOR_REVIEW,
            RecoveryCaseState.AWAITING_SECOND_APPROVAL,
        }:
            raise RecoveryError("illegal_transition", "Case is not ready for review assertions")
        if not case.evidence_hash:
            raise RecoveryError("evidence_required", "Evidence hash is required before assertions")

        expected = case.state_version
        snapshot_state = case.state
        snapshot_updated = case.updated_at
        snapshot_assertions = list(case.assertions)
        snapshot_version = case.state_version

        try:
            signed, _replayed = assertion_store.create(
                case_id=case.case_id,
                operation_key=operation_key,
                evidence_reference_hash=case.evidence_hash,
                asserted_supabase_user_id=case.subject_user_id,
                asserted_legacy_user_id=case.claimed_legacy_identity_ref,
                reviewer_id=reviewer_id,
                decision=decision,
                rationale_code=_rationale_to_code(rationale),
            )

            if signed.decision == AssertionDecision.REJECT:
                self._transition(
                    case,
                    RecoveryCaseState.REJECTED,
                    actor_id=reviewer_id,
                    operation_key=operation_key,
                    action="assert_reject",
                    detail={"assertion_id": str(signed.assertion_id)},
                )
            elif assertion_store.has_approval_quorum(
                case_id=case.case_id,
                evidence_reference_hash=case.evidence_hash,
            ):
                self._transition(
                    case,
                    RecoveryCaseState.APPROVED,
                    actor_id=reviewer_id,
                    operation_key=operation_key,
                    action="assert_approve_quorum",
                    detail={"assertion_id": str(signed.assertion_id)},
                )
            elif case.state == RecoveryCaseState.READY_FOR_REVIEW:
                self._transition(
                    case,
                    RecoveryCaseState.AWAITING_SECOND_APPROVAL,
                    actor_id=reviewer_id,
                    operation_key=operation_key,
                    action="assert_approve_first",
                    detail={"assertion_id": str(signed.assertion_id)},
                )
            else:
                case.updated_at = self._now()
                self._audit(
                    case_id=case.case_id,
                    actor_id=reviewer_id,
                    action="assert_approve",
                    from_state=case.state,
                    to_state=case.state,
                    operation_key=operation_key,
                    detail={"assertion_id": str(signed.assertion_id)},
                )

            self._persist(case, expected_version=expected, operation_key=operation_key)
            self._commit_tx()
        except RecoveryError as exc:
            self._rollback_tx()
            case.state = snapshot_state
            case.updated_at = snapshot_updated
            case.assertions = snapshot_assertions
            case.state_version = snapshot_version
            if exc.code == "four_eyes_conflict":
                try:
                    self._audit(
                        case_id=case.case_id,
                        actor_id=reviewer_id,
                        action="four_eyes_conflict",
                        from_state=case.state,
                        to_state=case.state,
                        operation_key=operation_key,
                        detail={"decision": decision},
                    )
                except Exception:
                    pass
            raise
        except Exception as exc:
            self._rollback_tx()
            case.state = snapshot_state
            case.updated_at = snapshot_updated
            case.assertions = snapshot_assertions
            case.state_version = snapshot_version
            raise self._rollback_audit_failure() from exc

        self._sync_case_assertions(case)
        return case, _signed_to_record(signed), False

    def revoke_assertion(
        self,
        *,
        case_id: UUID,
        assertion_id: UUID,
        reviewer_id: UUID,
        operation_key: str,
    ) -> tuple[RecoveryCaseRecord, SignedAssertion, bool]:
        """EC-02: revoke drops quorum immediately; case returns to reviewable state."""
        assertion_store = self._require_assertion_store()

        existing_op = self.store.get_case_id_for_operation(operation_key)
        if existing_op is not None:
            case = self.get_case(case_id)
            assertion = assertion_store.get(assertion_id)
            return case, assertion, True

        case = self.get_case(case_id)
        if case.state in TERMINAL_STATES:
            raise RecoveryError("terminal_case_immutable", "Terminal recovery cases cannot be mutated")

        expected = case.state_version
        snapshot_state = case.state
        snapshot_updated = case.updated_at
        snapshot_version = case.state_version
        try:
            assertion = assertion_store.revoke(assertion_id)
            if assertion.case_id != case.case_id:
                raise RecoveryError("assertion_not_found", "Assertion does not belong to this case")

            # A.3.4: after link create, assertion revoke invalidates the active link
            # in the same transaction and terminates the case as REVOKED.
            if case.state == RecoveryCaseState.LINK_CREATED:
                link_store = self._require_link_store()
                active = link_store.get_active_for_case(case.case_id)
                if active is not None:
                    link_store.revoke(
                        active.link_id,
                        revoked_by=reviewer_id,
                        reason="assertion_revoked_after_link",
                    )
                self._transition(
                    case,
                    RecoveryCaseState.REVOKED,
                    actor_id=reviewer_id,
                    operation_key=operation_key,
                    action="assert_revoke_invalidates_link",
                    detail={"assertion_id": str(assertion_id)},
                )
            elif case.state == RecoveryCaseState.REJECTED:
                # Reject is terminal; revoke does not reopen.
                self._audit(
                    case_id=case.case_id,
                    actor_id=reviewer_id,
                    action="assert_revoke",
                    from_state=case.state,
                    to_state=case.state,
                    operation_key=operation_key,
                    detail={"assertion_id": str(assertion_id)},
                )
            else:
                # Quorum must drop immediately for subsequent decisions.
                self._recompute_review_state(
                    case,
                    actor_id=reviewer_id,
                    operation_key=operation_key,
                    action="assert_revoke_quorum_drop",
                )
                if case.state == snapshot_state:
                    case.updated_at = self._now()
                    self._audit(
                        case_id=case.case_id,
                        actor_id=reviewer_id,
                        action="assert_revoke",
                        from_state=case.state,
                        to_state=case.state,
                        operation_key=operation_key,
                        detail={"assertion_id": str(assertion_id)},
                    )

            self._persist(case, expected_version=expected, operation_key=operation_key)
            self._commit_tx()
        except RecoveryError:
            self._rollback_tx()
            case.state = snapshot_state
            case.updated_at = snapshot_updated
            case.state_version = snapshot_version
            raise
        except Exception as exc:
            self._rollback_tx()
            case.state = snapshot_state
            case.updated_at = snapshot_updated
            case.state_version = snapshot_version
            raise self._rollback_audit_failure() from exc

        self._sync_case_assertions(case)
        return case, assertion, False

    def create_recovery_link(
        self,
        *,
        case_id: UUID,
        reviewer_id: UUID,
        operation_key: str,
    ) -> tuple[RecoveryCaseRecord, RecoveryLink, str | None, bool]:
        """Create a one-time recovery link after valid four-eyes quorum.

        Returns (case, link, raw_token|None, replayed). Raw token is present
        only on the first successful create for the operation_key.
        """
        assertion_store = self._require_assertion_store()
        link_store = self._require_link_store()

        existing = link_store.get_by_operation_key(operation_key)
        if existing is not None:
            case = self.get_case(case_id)
            if existing.case_id != case.case_id:
                raise RecoveryError(
                    "operation_key_conflict",
                    "operation_key already bound to a different recovery case",
                )
            self.store.bind_operation(operation_key, case.case_id)
            return case, existing, None, True

        case = self.get_case(case_id)
        if case.state in TERMINAL_STATES:
            raise RecoveryError("terminal_case_immutable", "Terminal recovery cases cannot be mutated")
        if case.state != RecoveryCaseState.APPROVED:
            raise RecoveryError(
                "illegal_transition",
                "Recovery link may only be created from APPROVED with valid quorum",
            )
        if not case.evidence_hash:
            raise RecoveryError("evidence_required", "Evidence hash is required before link create")

        if not assertion_store.has_approval_quorum(
            case_id=case.case_id,
            evidence_reference_hash=case.evidence_hash,
        ):
            expected = case.state_version
            snapshot_state = case.state
            snapshot_updated = case.updated_at
            snapshot_version = case.state_version
            try:
                self._transition(
                    case,
                    RecoveryCaseState.EXPIRED,
                    actor_id=reviewer_id,
                    operation_key=operation_key,
                    action="link_create_quorum_expired",
                    detail={"reason": "assertion_expired"},
                )
                self._persist(case, expected_version=expected, operation_key=operation_key)
                self._commit_tx()
            except Exception:
                self._rollback_tx()
                case.state = snapshot_state
                case.updated_at = snapshot_updated
                case.state_version = snapshot_version
            raise RecoveryError(
                "assertion_expired",
                "Expired or revoked assertions cannot satisfy quorum for link create",
            )

        expected = case.state_version
        snapshot_state = case.state
        snapshot_updated = case.updated_at
        snapshot_version = case.state_version
        try:
            link, raw_token, _ = link_store.create(
                case_id=case.case_id,
                operation_key=operation_key,
                evidence_reference_hash=case.evidence_hash,
                created_by=reviewer_id,
            )
            self._transition(
                case,
                RecoveryCaseState.LINK_CREATED,
                actor_id=reviewer_id,
                operation_key=operation_key,
                action="create_recovery_link",
                detail={"link_id": str(link.link_id)},
            )
            self._persist(case, expected_version=expected, operation_key=operation_key)
            self._commit_tx()
        except RecoveryError:
            self._rollback_tx()
            case.state = snapshot_state
            case.updated_at = snapshot_updated
            case.state_version = snapshot_version
            raise
        except Exception as exc:
            self._rollback_tx()
            case.state = snapshot_state
            case.updated_at = snapshot_updated
            case.state_version = snapshot_version
            raise self._rollback_audit_failure() from exc

        return case, link, raw_token, False

    def revoke_recovery_link(
        self,
        *,
        case_id: UUID,
        reviewer_id: UUID,
        operation_key: str,
        reason: str,
        link_id: UUID | None = None,
    ) -> tuple[RecoveryCaseRecord, RecoveryLink, bool]:
        """Revoke a recovery link. Reason required. Idempotent on operation_key / already-revoked."""
        link_store = self._require_link_store()

        existing_op = self.store.get_case_id_for_operation(operation_key)
        if existing_op is not None:
            case = self.get_case(case_id)
            if link_id is not None:
                link = link_store.get(link_id)
            else:
                links = link_store.list_for_case(case.case_id)
                if not links:
                    raise RecoveryError("link_not_found", "No recovery link found for case")
                link = links[-1]
            return case, link, True

        case = self.get_case(case_id)
        if case.state not in {RecoveryCaseState.LINK_CREATED, RecoveryCaseState.REVOKED}:
            if case.state in TERMINAL_STATES:
                raise RecoveryError(
                    "terminal_case_immutable",
                    "Terminal recovery cases cannot be mutated",
                )
            raise RecoveryError(
                "illegal_transition",
                "Recovery link revoke requires LINK_CREATED (or idempotent REVOKED)",
            )

        if link_id is not None:
            link = link_store.get(link_id)
            if link.case_id != case.case_id:
                raise RecoveryError("link_not_found", "Recovery link does not belong to this case")
        else:
            # Prefer active; fall back to latest link for idempotent revoke.
            link = link_store.get_active_for_case(case.case_id)
            if link is None:
                links = link_store.list_for_case(case.case_id)
                if not links:
                    raise RecoveryError("link_not_found", "No recovery link found for case")
                link = links[-1]

        expected = case.state_version
        snapshot_state = case.state
        snapshot_updated = case.updated_at
        snapshot_version = case.state_version
        try:
            revoked_link, already = link_store.revoke(
                link.link_id,
                revoked_by=reviewer_id,
                reason=reason,
            )
            if case.state == RecoveryCaseState.LINK_CREATED:
                self._transition(
                    case,
                    RecoveryCaseState.REVOKED,
                    actor_id=reviewer_id,
                    operation_key=operation_key,
                    action="revoke_recovery_link",
                    detail={
                        "link_id": str(revoked_link.link_id),
                        "reason": reason.strip(),
                        "already_revoked": already,
                    },
                )
            else:
                case.updated_at = self._now()
                self._audit(
                    case_id=case.case_id,
                    actor_id=reviewer_id,
                    action="revoke_recovery_link",
                    from_state=case.state,
                    to_state=case.state,
                    operation_key=operation_key,
                    detail={
                        "link_id": str(revoked_link.link_id),
                        "reason": reason.strip(),
                        "already_revoked": True,
                    },
                )
            self._persist(case, expected_version=expected, operation_key=operation_key)
            self._commit_tx()
        except RecoveryError:
            self._rollback_tx()
            case.state = snapshot_state
            case.updated_at = snapshot_updated
            case.state_version = snapshot_version
            raise
        except Exception as exc:
            self._rollback_tx()
            case.state = snapshot_state
            case.updated_at = snapshot_updated
            case.state_version = snapshot_version
            raise self._rollback_audit_failure() from exc

        return case, revoked_link, False

    def cancel_case(
        self,
        *,
        case_id: UUID,
        reviewer_id: UUID,
        operation_key: str,
        reason: str,
    ) -> tuple[RecoveryCaseRecord, bool]:
        existing = self.store.get_case_id_for_operation(operation_key)
        if existing is not None:
            return self.get_case(existing), True

        case = self.get_case(case_id)
        if case.state in TERMINAL_STATES:
            raise RecoveryError("terminal_case_immutable", "Terminal recovery cases cannot be mutated")

        expected = case.state_version
        snapshot_state = case.state
        snapshot_updated = case.updated_at
        snapshot_version = case.state_version
        try:
            self._transition(
                case,
                RecoveryCaseState.CANCELLED,
                actor_id=reviewer_id,
                operation_key=operation_key,
                action="cancel_case",
                detail={"reason": reason},
            )
            self._persist(case, expected_version=expected, operation_key=operation_key)
            self._commit_tx()
        except RecoveryError:
            self._rollback_tx()
            case.state = snapshot_state
            case.updated_at = snapshot_updated
            case.state_version = snapshot_version
            raise
        except Exception as exc:
            self._rollback_tx()
            case.state = snapshot_state
            case.updated_at = snapshot_updated
            case.state_version = snapshot_version
            raise self._rollback_audit_failure() from exc

        return case, False


_default_store = RecoveryStore()
_default_audit = InMemoryAuditWriter()
default_recovery_service = RecoveryService(_default_store, _default_audit)
