import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class V1Conversation(Base):
    __tablename__ = "v1_conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(30), nullable=False, default="aura")
    intent: Mapped[str] = mapped_column(String(30), nullable=False, default="build")
    work_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="deep_work")
    session_goal: Mapped[str | None] = mapped_column(String(500))
    emotional_climate: Mapped[str | None] = mapped_column(String(50))
    reflection_after_action: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    messages: Mapped[list["V1Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="V1Message.created_at")


class V1Message(Base):
    __tablename__ = "v1_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("v1_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    memory_suggestions: Mapped[list[dict] | None] = mapped_column(JSON)
    progress_report: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    conversation: Mapped[V1Conversation] = relationship(back_populates="messages")


class V1Memory(Base):
    __tablename__ = "v1_memories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False, default="explicit")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class V1AuraState(Base):
    __tablename__ = "v1_aura_states"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    current_focus: Mapped[str | None] = mapped_column(String(500))
    energy_level: Mapped[str | None] = mapped_column(String(100))
    active_project: Mapped[str | None] = mapped_column(String(300))
    last_checkpoint: Mapped[str | None] = mapped_column(Text)
    relationship_style: Mapped[str] = mapped_column(String(100), nullable=False, default="Strategic Partner")
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class V1Project(Base):
    __tablename__ = "v1_projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    current_sprint: Mapped[str | None] = mapped_column(String(200))
    next_step: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[list | None] = mapped_column(JSON)
    decisions: Mapped[list | None] = mapped_column(JSON)
    manifestos: Mapped[list | None] = mapped_column(JSON)
    risks: Mapped[list | None] = mapped_column(JSON)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
