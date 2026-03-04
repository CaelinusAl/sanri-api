from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.models.base import Base


class DailyStream(Base):
    __tablename__ = "daily_stream"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, unique=True, index=True)
    message = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class WeeklySymbol(Base):
    __tablename__ = "weekly_symbol"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    week = Column(String, unique=True, index=True)
    symbol = Column(String)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)