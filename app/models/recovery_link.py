"""Durable recovery link rows (PMP-01A.3.4).

Raw tokens are never stored — only token_hash.
"""

import uuid

from sqlalchemy import DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class V1RecoveryLink(Base):
    __tablename__ = "v1_recovery_links"

    link_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    operation_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_reference_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    revoke_reason: Mapped[str | None] = mapped_column(Text)
    used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
