# app/models/daily_stream.py
from datetime import datetime, date
from sqlalchemy import Column, String, DateTime, Date, Text, UniqueConstraint
from app.db import Base

class DailyStream(Base):
    __tablename__ = "daily_stream"
    __table_args__ = {"extend_existing": True}

    id = Column(String, primary_key=True) # uuid
    day = Column(Date, nullable=False, index=True) # UTC date
    lang = Column(String, nullable=False, default="tr", index=True) # tr/en
    kicker = Column(String, nullable=False, default="")
    title = Column(String, nullable=False, default="")
    subtitle = Column(String, nullable=True)
    body = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("day", "lang", name="uq_daily_stream_day_lang"),
    )


class WeeklySymbol(Base):
    __tablename__ = "weekly_symbol"
    __table_args__ = {"extend_existing": True}
    

    id = Column(String, primary_key=True) # uuid
    week_key = Column(String, nullable=False, index=True) # "2026-W10"
    lang = Column(String, nullable=False, default="tr", index=True)
    title = Column(String, nullable=False, default="")
    subtitle = Column(String, nullable=True)
    body = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("week_key", "lang", name="uq_weekly_symbol_week_lang"),
    )