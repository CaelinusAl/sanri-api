"""Durable Recovery Case Ledger (PMP-01A.3.6).

Authority rules:
- Case state is server-authoritative; clients cannot reconstruct authority.
- At most one non-terminal case per subject_user_id / legacy identity.
- Concurrent mutations fail closed via state_version compare-and-set.
- operation_key replay is restart-safe.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.assertion_signing import as_utc
from app.domain.recovery import TERMINAL_STATES, RecoveryCaseState, RecoveryError
from app.models.recovery_case import V1RecoveryCase, V1RecoveryCaseOperation


class DurableRecoveryCaseStore:
    def __init__(self, session: Session):
        self.session = session
        # Compatibility surface for harnesses that inspect dict mirrors.
        self.cases: dict[UUID, object] = {}
        self.operations: dict[str, UUID] = {}

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _to_record(self, row: V1RecoveryCase):
        # Local import avoids circular dependency with recovery_service.
        from app.application.recovery_service import RecoveryCaseRecord

        record = RecoveryCaseRecord(
            case_id=row.case_id,
            state=RecoveryCaseState(row.state),
            subject_user_id=row.subject_user_id,
            claimed_legacy_identity_ref=row.claimed_legacy_identity_ref,
            created_by=row.created_by,
            evidence_hash=row.evidence_hash,
            evidence_type=row.evidence_type,
            notes=row.notes,
            created_at=as_utc(row.created_at),
            updated_at=as_utc(row.updated_at),
            expires_at=as_utc(row.expires_at) if row.expires_at is not None else None,
            assertions=[],
            state_version=int(row.state_version),
        )
        self.cases[record.case_id] = record
        return record

    def get(self, case_id: UUID):
        row = self.session.get(V1RecoveryCase, case_id)
        if row is None:
            return None
        return self._to_record(row)

    def get_case_id_for_operation(self, operation_key: str) -> UUID | None:
        row = self.session.scalar(
            select(V1RecoveryCaseOperation).where(
                V1RecoveryCaseOperation.operation_key == operation_key
            )
        )
        if row is None:
            return self.operations.get(operation_key)
        self.operations[operation_key] = row.case_id
        return row.case_id

    def list_open_for_identity(
        self,
        *,
        subject_user_id: UUID,
        claimed_legacy_identity_ref: str,
    ) -> list:
        terminal = {str(s) for s in TERMINAL_STATES}
        rows = self.session.scalars(
            select(V1RecoveryCase).where(
                or_(
                    V1RecoveryCase.subject_user_id == subject_user_id,
                    V1RecoveryCase.claimed_legacy_identity_ref == claimed_legacy_identity_ref,
                )
            )
        ).all()
        return [self._to_record(row) for row in rows if row.state not in terminal]

    def bind_operation(self, operation_key: str, case_id: UUID) -> None:
        existing = self.get_case_id_for_operation(operation_key)
        if existing is not None:
            if existing != case_id:
                raise RecoveryError(
                    "operation_key_conflict",
                    "operation_key already bound to a different recovery case",
                )
            return
        self.session.add(
            V1RecoveryCaseOperation(
                operation_key=operation_key,
                case_id=case_id,
                created_at=self._now(),
            )
        )
        self.operations[operation_key] = case_id
        self.session.flush()

    def create(self, case, *, operation_key: str):
        if self.get(case.case_id) is not None:
            raise RecoveryError("conflict_state", "Recovery case already exists")
        if self.list_open_for_identity(
            subject_user_id=case.subject_user_id,
            claimed_legacy_identity_ref=case.claimed_legacy_identity_ref,
        ):
            raise RecoveryError(
                "duplicate_open_case",
                "At most one non-terminal recovery case per subject or legacy identity",
            )

        case.state_version = 0
        row = V1RecoveryCase(
            case_id=case.case_id,
            state=str(case.state),
            subject_user_id=case.subject_user_id,
            claimed_legacy_identity_ref=case.claimed_legacy_identity_ref,
            created_by=case.created_by,
            evidence_hash=case.evidence_hash,
            evidence_type=case.evidence_type,
            notes=case.notes,
            created_at=case.created_at,
            updated_at=case.updated_at,
            expires_at=case.expires_at,
            state_version=case.state_version,
        )
        try:
            self.session.add(row)
            self.session.flush()
            self.bind_operation(operation_key, case.case_id)
        except IntegrityError as exc:
            raise RecoveryError(
                "duplicate_open_case",
                "At most one non-terminal recovery case per subject or legacy identity",
            ) from exc
        return self._to_record(row)

    def save(self, case, *, expected_version: int, operation_key: str | None = None):
        # Expire cached identity so concurrent winners are visible before CAS.
        self.session.expire_all()
        row = self.session.get(V1RecoveryCase, case.case_id)
        if row is None:
            raise RecoveryError("case_not_found", "Recovery case not found")
        if row.state in {str(s) for s in TERMINAL_STATES} and str(case.state) not in {
            str(s) for s in TERMINAL_STATES
        }:
            raise RecoveryError(
                "terminal_case_immutable",
                "Terminal recovery cases cannot be mutated",
            )

        try:
            result = self.session.execute(
                update(V1RecoveryCase)
                .where(
                    V1RecoveryCase.case_id == case.case_id,
                    V1RecoveryCase.state_version == expected_version,
                )
                .values(
                    state=str(case.state),
                    evidence_hash=case.evidence_hash,
                    evidence_type=case.evidence_type,
                    notes=case.notes,
                    updated_at=case.updated_at,
                    expires_at=case.expires_at,
                    state_version=expected_version + 1,
                )
            )
        except IntegrityError as exc:
            raise RecoveryError(
                "duplicate_open_case",
                "At most one non-terminal recovery case per subject or legacy identity",
            ) from exc

        if result.rowcount != 1:
            raise RecoveryError(
                "conflict_state",
                "Concurrent case mutation rejected; reload and retry",
            )
        self.session.flush()

        if operation_key is not None:
            self.bind_operation(operation_key, case.case_id)

        self.session.expire_all()
        refreshed = self.get(case.case_id)
        if refreshed is None:
            raise RecoveryError("case_not_found", "Recovery case not found")
        case.state_version = refreshed.state_version
        return refreshed
