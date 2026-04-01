from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from app.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # cihaz / local kimlik
    external_id = Column(String, unique=True, index=True, nullable=True)

    # auth
    email = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False, nullable=False)

    # profil
    name = Column(String, nullable=True)
    birth_date = Column(String, nullable=True)

    # erişim rolü / plan
    role = Column(String, default="free", nullable=False)
    plan = Column(String, default="free", nullable=False)

    # premium subscription
    is_premium = Column(Boolean, default=False, nullable=False)
    premium_until = Column(DateTime, nullable=True)
    premium_source = Column(String, nullable=True)  # stripe / revenuecat / admin
    stripe_customer_id = Column(String, nullable=True, unique=True, index=True)
    apple_product_id = Column(String, nullable=True)
    apple_original_transaction_id = Column(String, nullable=True, index=True)

    # tek seferlik kilit açma
    matrix_role_unlocked = Column(Boolean, default=False, nullable=False)
    free_unlock_used = Column(Boolean, default=False, nullable=False)

    # kullanım / aktivite
    last_matrix_deep_analysis = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)

    # hesap silme akışı
    deletion_requested_at = Column(DateTime, nullable=True)
    account_deleted_at = Column(DateTime, nullable=True)

    # Yanki profile extensions
    display_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    bio = Column(Text, nullable=True)

    # Streak tracking
    last_active_date = Column(String, nullable=True)
    current_streak = Column(Integer, default=0, nullable=False)
    longest_streak = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)