"""Anlaşılma Alanı — anonim frekans + niyet (user_id yok, session_id)."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.db import Base


class AnlasilmaPresence(Base):
    __tablename__ = "anlasilma_presence"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(80), unique=True, index=True, nullable=False)
    frequency_hz = Column(Integer, nullable=False, index=True)
    intent_text = Column(String(200), nullable=False)
    emotion_tags = Column(Text, nullable=True)  # JSON array string
    embedding_json = Column(Text, nullable=True)  # JSON list[float]
    wants_chat = Column(Boolean, default=False, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AnlasilmaChatRoom(Base):
    __tablename__ = "anlasilma_chat_rooms"

    id = Column(Integer, primary_key=True, index=True)
    session_a = Column(String(80), nullable=False, index=True)
    session_b = Column(String(80), nullable=False, index=True)
    frequency_hz = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class AnlasilmaChatMessage(Base):
    __tablename__ = "anlasilma_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, nullable=False, index=True)
    from_session = Column(String(80), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
