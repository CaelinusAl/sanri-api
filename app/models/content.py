# app/models/content.py
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, JSON, UniqueConstraint
from app.db import Base

class WeeklySymbol(Base):
    __tablename__ = "weekly_symbols"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    week_key = Column(String, nullable=False, index=True) # e.g. "2026-W10"
    title = Column(String, nullable=False)
    subtitle = Column(String, nullable=True)
    body_tr = Column(Text, nullable=False)
    body_en = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("week_key", name="uq_week_key"),)