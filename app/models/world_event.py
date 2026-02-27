import uuid
from sqlalchemy import Column, String, DateTime, Text, Boolean
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from app.db import Base

class WorldEvent(Base):
    __tablename__ = "world_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(300), nullable=False)
    source_url = Column(String(1200), nullable=True)
    user_note = Column(Text, nullable=True)

    # Senin/Sanrı'nın ana okuma metni
    reading_tr = Column(Text, nullable=False)
    reading_en = Column(Text, nullable=True)

    # Etiketler + meta (JSON sqlite’da da çalışır)
    tags = Column(JSON, nullable=True)   # ["tutulma","6","denge",...]
    meta = Column(JSON, nullable=True)   # {"type":"tutulma","year_range":"2026-2028",...}

    status = Column(String(32), nullable=False, default="draft")  # draft|published|archived
    is_pinned = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)