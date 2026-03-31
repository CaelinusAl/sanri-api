from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db import Base


class SanriReflection(Base):
    __tablename__ = "sanri_reflections"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("yanki_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    source = Column(String(20), nullable=False, default="api")  # "api" | "fallback"

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    post = relationship("YankiPost", back_populates="reflections")
    user = relationship("User", foreign_keys=[user_id], lazy="select")

    def to_dict(self):
        return {
            "id": self.id,
            "post_id": self.post_id,
            "user_id": self.user_id,
            "prompt": self.prompt,
            "response": self.response,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
