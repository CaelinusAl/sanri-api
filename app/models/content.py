# app/models/content.py
import uuid
from datetime import datetime, date
from sqlalchemy import Column, String, DateTime, Date, Text, UniqueConstraint
from app.models.base import Base

class DailyStream(Base):
    __tablename__ = "daily_stream"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    day = Column(Date, nullable=False) # date.today()
    lang = Column(String, nullable=False) # "tr" | "en"

    title = Column(String, nullable=True)
    message = Column(Text, nullable=False) # ana akış
    short = Column(Text, nullable=True) # 1 cümle özet
    tags = Column(Text, nullable=True) # json string

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("day", "lang", name="uq_daily_stream_day_lang"),
    )

class WeeklySymbol(Base):
    __tablename__ = "weekly_symbol"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    week_key = Column(String, nullable=False) # "YYYY-WW"
    lang = Column(String, nullable=False)

    title = Column(String, nullable=False)
    subtitle = Column(String, nullable=True)
    reading = Column(Text, nullable=False) # uzun metin
    tags = Column(Text, nullable=True) # json string

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("week_key", "lang", name="uq_weekly_symbol_week_lang"),
    )