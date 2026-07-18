"""Durable recovery audit ledger rows (PMP-01A.3.7).

Append-only at the database layer (PostgreSQL trigger). Application code
only inserts; updates/deletes are rejected by the trigger.
"""

import uuid

from sqlalchemy import DateTime, JSON, String, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class V1RecoveryAuditEvent(Base):
    __tablename__ = "v1_recovery_audit_events"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "operation_key",
            "event_type",
            name="v1_recovery_audit_events_case_op_type_uq",
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    operation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    from_state: Mapped[str | None] = mapped_column(String(64))
    to_state: Mapped[str | None] = mapped_column(String(64))
    entity_ref: Mapped[str | None] = mapped_column(String(128))
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
