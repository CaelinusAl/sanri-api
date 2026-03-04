# app/models/system_feed.py
import uuid
import time
from sqlalchemy import Column, String, Text, Integer
from app.models.base import Base

class SystemFeedItem(Base):
    __tablename__ = "system_feed_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(Integer, nullable=False, default=lambda: int(time.time()))

    # "daily", "world", "weekly" gibi
    kind = Column(String(32), nullable=False, default="world")

    title = Column(String(220), nullable=False, default="")
    subtitle = Column(String(220), nullable=False, default="")
    body_tr = Column(Text, nullable=False, default="")
    body_en = Column(Text, nullable=False, default="")

    # kaynak/kanıt
    source_url = Column(String(500), nullable=False, default="")
    tags = Column(String(500), nullable=False, default="") # "tag1,tag2"