from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Index, Text
)
from app.db import Base


class Subscription(Base):
    """Stripe subscription lifecycle records."""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    stripe_customer_id = Column(String, nullable=False, index=True)
    stripe_subscription_id = Column(String, unique=True, nullable=False, index=True)
    stripe_price_id = Column(String, nullable=False)
    product_key = Column(String, nullable=False)

    status = Column(String, default="active", nullable=False)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    canceled_at = Column(DateTime, nullable=True)
    failure_reason = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Purchase(Base):
    """One-time payments (single unlock, weekly pass)."""
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    stripe_customer_id = Column(String, nullable=True)
    stripe_session_id = Column(String, unique=True, nullable=False, index=True)
    stripe_payment_intent_id = Column(String, nullable=True, index=True)

    product_key = Column(String, nullable=False)
    content_id = Column(String, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="try", nullable=False)
    status = Column(String, default="pending", nullable=False)
    failure_reason = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_purchases_user_product", "user_id", "product_key"),
    )


class ContentUnlock(Base):
    """Per-content unlock records (from single purchases)."""
    __tablename__ = "content_unlocks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content_id = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True)

    unlocked_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_content_unlocks_user_content", "user_id", "content_id", unique=True),
    )


class UserEntitlement(Base):
    """
    Unified entitlement layer.

    Each row = one active entitlement a user holds.
    Sources: stripe, revenuecat, admin_grant, promo.
    RevenueCat sync writes to this same table via POST /billing/sync-entitlements.

    entitlement_key examples:
      - premium_access         (from premium_monthly / premium_yearly)
      - weekly_access           (from weekly_pass, expires)
      - content:okuma:<id>     (from single_read_unlock)
      - content:book:<id>      (from single_book_unlock)
      - content:ritual:<id>    (from single_ritual_unlock)
    """
    __tablename__ = "user_entitlements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    entitlement_key = Column(String, nullable=False)
    product_key = Column(String, nullable=True)
    source = Column(String, nullable=False, default="stripe")

    is_active = Column(Boolean, default=True, nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    stripe_subscription_id = Column(String, nullable=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True)
    metadata_json = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_entitlements_user_key", "user_id", "entitlement_key"),
        Index("ix_entitlements_active", "user_id", "is_active"),
    )
