from sqlalchemy import Column, Integer, String, DateTime, func
from app.models.base import Base


class FunnelEvent(Base):
    __tablename__ = "funnel_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False, index=True)
    user_id = Column(String(128), nullable=True)
    session_id = Column(String(128), nullable=True)
    source = Column(String(64), nullable=True, default="direct")
    device_type = Column(String(32), nullable=True, default="unknown")
    extra = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
