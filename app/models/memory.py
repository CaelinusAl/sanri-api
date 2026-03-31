from sqlalchemy import Column, String, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.db import Base


class Memory(Base):
    __tablename__ = "memories"

    id = Column(String, primary_key=True, index=True, default=lambda: __import__("uuid").uuid4().hex)
    user_id = Column(String, nullable=False, index=True)

    type = Column(String, nullable=False, default="auto")
    context = Column(JSON, nullable=True)

    input_text = Column(Text, nullable=False)
    output_text = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())