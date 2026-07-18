"""Durable recovery case ledger rows (PMP-01A.3.6)."""

import uuid

from sqlalchemy import DateTime, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class V1RecoveryCase(Base):
    __tablename__ = "v1_recovery_cases"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    claimed_legacy_identity_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    evidence_hash: Mapped[str | None] = mapped_column(String(128))
    evidence_type: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class V1RecoveryCaseOperation(Base):
    """Global idempotency map for recovery case mutations (and resume keys)."""

    __tablename__ = "v1_recovery_case_operations"

    operation_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
