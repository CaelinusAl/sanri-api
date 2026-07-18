"""Durable Recovery Audit Ledger (PMP-01A.3.7).

Authority rules:
- Append-only inserts; never UPDATE/DELETE from application code.
- write() only flushes; RecoveryService owns commit/rollback.
- Idempotency scope is UNIQUE(case_id, operation_key, event_type).
- Detail metadata is allowlisted; secrets/tokens never persist.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.assertion_signing import as_utc
from app.domain.recovery import RecoveryError
from app.models.recovery_audit import V1RecoveryAuditEvent

# Explicit allowlist — never persist raw tokens, secrets, JWTs, or full evidence.
AUDIT_DETAIL_ALLOWLIST = frozenset(
    {
        "subject_user_id",
        "evidence_type",
        "reason",
        "assertion_id",
        "decision",
        "link_id",
        "already_revoked",
    }
)

_SCOPED_UQ_NAME = "v1_recovery_audit_events_case_op_type_uq"
_MAX_DETAIL_STR_LEN = 256


def sanitize_audit_detail(detail: dict | None) -> dict[str, Any]:
    """Keep only allowlisted scalar metadata suitable for durable audit."""
    if not detail:
        return {}
    out: dict[str, Any] = {}
    for key, value in detail.items():
        if key not in AUDIT_DETAIL_ALLOWLIST:
            continue
        if value is None or isinstance(value, bool):
            out[key] = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = value
        elif isinstance(value, UUID):
            out[key] = str(value)
        elif isinstance(value, str):
            out[key] = value[:_MAX_DETAIL_STR_LEN]
        # Drop nested structures, bytes, and other unsafe types.
    return out


def entity_ref_from_detail(detail: dict[str, Any]) -> str | None:
    if assertion_id := detail.get("assertion_id"):
        return f"assertion:{assertion_id}"
    if link_id := detail.get("link_id"):
        return f"link:{link_id}"
    return None


def _is_scoped_idempotency_conflict(exc: IntegrityError) -> bool:
    """True only for UNIQUE(case_id, operation_key, event_type) conflicts."""
    msg = str(getattr(exc, "orig", None) or exc).lower()
    if _SCOPED_UQ_NAME in msg:
        return True
    # SQLite: UNIQUE constraint failed: table.col, table.col, table.col
    if "unique" in msg and "v1_recovery_audit_events" in msg:
        return (
            "case_id" in msg
            and "operation_key" in msg
            and "event_type" in msg
        )
    return False


class DurableAuditWriter:
    """Session-bound append-only audit writer (flush only)."""

    def __init__(self, session: Session, *, fail: bool = False):
        if session is None:
            raise RecoveryError(
                "audit_unavailable",
                "Durable audit writer requires a database session",
            )
        self.session = session
        self.fail = fail
        # Compatibility mirror for harnesses that inspect .records
        self.records: list = []

    def _to_record(self, row: V1RecoveryAuditEvent):
        # Local import avoids circular dependency with recovery_service.
        from app.application.recovery_service import AuditRecord

        record = AuditRecord(
            audit_id=row.event_id,
            case_id=row.case_id,
            actor_id=row.actor_id,
            action=row.event_type,
            from_state=row.from_state,
            to_state=row.to_state,
            operation_key=row.operation_key,
            created_at=as_utc(row.created_at),
            detail=dict(row.detail or {}),
            entity_ref=row.entity_ref,
        )
        return record

    def get_by_scope(
        self,
        *,
        case_id: UUID,
        operation_key: str,
        event_type: str,
    ):
        row = self.session.scalar(
            select(V1RecoveryAuditEvent).where(
                V1RecoveryAuditEvent.case_id == case_id,
                V1RecoveryAuditEvent.operation_key == operation_key,
                V1RecoveryAuditEvent.event_type == event_type,
            )
        )
        return self._to_record(row) if row is not None else None

    def list_for_case(self, case_id: UUID) -> list:
        rows = self.session.scalars(
            select(V1RecoveryAuditEvent)
            .where(V1RecoveryAuditEvent.case_id == case_id)
            .order_by(V1RecoveryAuditEvent.created_at.asc())
        ).all()
        return [self._to_record(r) for r in rows]

    def list_by_operation_key(self, operation_key: str) -> list:
        rows = self.session.scalars(
            select(V1RecoveryAuditEvent)
            .where(V1RecoveryAuditEvent.operation_key == operation_key)
            .order_by(V1RecoveryAuditEvent.created_at.asc())
        ).all()
        return [self._to_record(r) for r in rows]

    def write(self, record) -> None:
        if self.fail:
            raise RuntimeError("audit_write_failed")

        detail = sanitize_audit_detail(getattr(record, "detail", None))
        entity_ref = getattr(record, "entity_ref", None) or entity_ref_from_detail(detail)
        event_type = record.action
        case_id = record.case_id
        operation_key = record.operation_key

        existing = self.get_by_scope(
            case_id=case_id,
            operation_key=operation_key,
            event_type=event_type,
        )
        if existing is not None:
            self.records.append(existing)
            return

        row = V1RecoveryAuditEvent(
            event_id=record.audit_id,
            event_type=event_type,
            case_id=case_id,
            operation_key=operation_key,
            actor_id=record.actor_id,
            created_at=record.created_at,
            from_state=record.from_state,
            to_state=record.to_state,
            entity_ref=entity_ref,
            detail=detail,
        )
        try:
            with self.session.begin_nested():
                self.session.add(row)
                self.session.flush()
        except IntegrityError as exc:
            if not _is_scoped_idempotency_conflict(exc):
                raise
            raced = self.get_by_scope(
                case_id=case_id,
                operation_key=operation_key,
                event_type=event_type,
            )
            if raced is None:
                raise RecoveryError(
                    "audit_failed",
                    "Scoped audit uniqueness conflict without recoverable row",
                ) from exc
            self.records.append(raced)
            return

        persisted = self._to_record(row)
        self.records.append(persisted)
