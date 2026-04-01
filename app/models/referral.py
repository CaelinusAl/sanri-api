from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from app.db import Base


class YankiReferral(Base):
    __tablename__ = "yanki_referrals"

    id = Column(Integer, primary_key=True, index=True)
    referrer_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    invited_user_id = Column(Integer, nullable=True)
    post_id = Column(Integer, ForeignKey("yanki_posts.id", ondelete="SET NULL"), nullable=True)
    visitor_fingerprint = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_referral_referrer", "referrer_user_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "referrer_user_id": self.referrer_user_id,
            "invited_user_id": self.invited_user_id,
            "post_id": self.post_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
