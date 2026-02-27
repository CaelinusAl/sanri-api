from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.sql import func
from app.db import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=True)

    action = Column(String, nullable=False)     # ask, login, register, world_event vs
    domain = Column(String, nullable=True)      # auto, matrix, awakened_cities, etc

    meta = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())