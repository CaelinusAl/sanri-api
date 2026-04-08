import uuid
from datetime import datetime, date
from sqlalchemy import Column, String, DateTime, Date, Text, Integer, UniqueConstraint
from app.models.base import Base


class DailyFeeling(Base):
    __tablename__ = "daily_feelings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    day = Column(Date, nullable=False)
    period = Column(String(10), nullable=False, default="morning")

    top_frequency = Column(Integer, nullable=True)
    top_tags = Column(Text, nullable=True)
    active_count = Column(Integer, nullable=True, default=0)
    feeling_text_tr = Column(Text, nullable=True)
    feeling_text_en = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("day", "period", name="uq_daily_feeling_day_period"),
    )
