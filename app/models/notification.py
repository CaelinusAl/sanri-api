from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from app.db import Base


class YankiNotification(Base):
    __tablename__ = "yanki_notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(30), nullable=False)  # "comment" | "reaction" | "sanri"
    post_id = Column(Integer, ForeignKey("yanki_posts.id", ondelete="CASCADE"), nullable=True)
    actor_id = Column(Integer, nullable=True)
    message = Column(String(500), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_notif_user_unread", "user_id", "is_read"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "post_id": self.post_id,
            "actor_id": self.actor_id,
            "message": self.message,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
