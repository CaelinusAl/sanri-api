from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from app.db import Base


class YankiPost(Base):
    __tablename__ = "yanki_posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Maps to old "author_mode" column -- kept as VARCHAR for backward compat
    author_mode = Column(String(20), default="anonymous", nullable=False)
    # Maps to old "category" column
    category = Column(String(50), default="genel", nullable=False)

    title = Column(String(300), nullable=True)
    content_raw = Column(Text, nullable=False)
    content_sanitized = Column(Text, nullable=True)

    image_url = Column(String, nullable=True)
    audio_url = Column(String, nullable=True)

    # Maps to old "status" column
    status = Column(String(20), default="pending_review", nullable=False)
    sanri_note = Column(Text, nullable=True)
    reject_reason = Column(Text, nullable=True)

    # Denormalized counters (kept for fast reads, same pattern as before)
    reaction_heart = Column(Integer, default=0, nullable=False)
    reaction_felt = Column(Integer, default=0, nullable=False)
    reaction_sessizce = Column(Integer, default=0, nullable=False)
    report_count = Column(Integer, default=0, nullable=False)
    comment_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)

    # ORM relationships -- lazy="select" avoids JOIN issues with missing columns
    user = relationship("User", foreign_keys=[user_id], lazy="select")
    comments = relationship("YankiComment", back_populates="post", lazy="dynamic", cascade="all, delete-orphan")
    reactions = relationship("YankiReaction", back_populates="post", lazy="dynamic", cascade="all, delete-orphan")
    reports = relationship("YankiReport", back_populates="post", lazy="dynamic", cascade="all, delete-orphan")
    reflections = relationship("SanriReflection", back_populates="post", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def is_anonymous(self):
        return self.author_mode == "anonymous"

    @property
    def is_published(self):
        return self.status == "published"

    def _safe_author_name(self):
        try:
            if self.is_anonymous or not self.user:
                return None
            return getattr(self.user, "display_name", None) or getattr(self.user, "name", None)
        except Exception:
            return None

    def to_public_dict(self):
        return {
            "id": self.id,
            "author_mode": self.author_mode,
            "author_name": self._safe_author_name(),
            "title": self.title,
            "content": self.content_sanitized or self.content_raw,
            "category": self.category,
            "image_url": self.image_url,
            "audio_url": self.audio_url,
            "sanri_note": self.sanri_note,
            "reaction_heart": self.reaction_heart,
            "reaction_felt": self.reaction_felt,
            "reaction_sessizce": self.reaction_sessizce,
            "comment_count": self.comment_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }

    def to_admin_dict(self):
        d = self.to_public_dict()
        d.update({
            "user_id": self.user_id,
            "content_raw": self.content_raw,
            "status": self.status,
            "reject_reason": self.reject_reason,
            "report_count": self.report_count,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        })
        return d


class YankiComment(Base):
    __tablename__ = "yanki_comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("yanki_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    post = relationship("YankiPost", back_populates="comments")
    user = relationship("User", foreign_keys=[user_id], lazy="select")

    def to_dict(self):
        try:
            author_name = (getattr(self.user, "display_name", None) or getattr(self.user, "name", None)) if self.user else None
        except Exception:
            author_name = None
        return {
            "id": self.id,
            "post_id": self.post_id,
            "user_id": self.user_id,
            "author_name": author_name,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class YankiReaction(Base):
    __tablename__ = "yanki_reactions"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("yanki_posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, nullable=True)
    reaction_type = Column(String(30), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", "reaction_type", name="uq_yanki_reaction"),
        Index("ix_yanki_reaction_lookup", "post_id", "user_id", "reaction_type"),
    )

    post = relationship("YankiPost", back_populates="reactions")


class YankiReport(Base):
    __tablename__ = "yanki_reports"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("yanki_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    post = relationship("YankiPost", back_populates="reports")
