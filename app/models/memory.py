from sqlalchemy import Column, String, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.db import Base


class Memory(Base):
    __tablename__ = "memories"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=True)

    type = Column(String, nullable=True)        # matrix, world_events, auto
    context = Column(JSON, nullable=True)

    input_text = Column(Text, nullable=False)
    output_text = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())