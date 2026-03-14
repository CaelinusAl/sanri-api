from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # cihaz / local kimlik
    external_id = Column(String, unique=True, index=True, nullable=False)

    # profil
    name = Column(String, nullable=True)
    birth_date = Column(String, nullable=True)

    # erişim rolü
    role = Column(String, default="free", nullable=False)

    # premium subscription
    is_premium = Column(Boolean, default=False, nullable=False)
    premium_until = Column(DateTime, nullable=True)
    premium_source = Column(String, nullable=True) # apple / google / admin
    apple_product_id = Column(String, nullable=True)
    apple_original_transaction_id = Column(String, nullable=True, index=True)

    # tek seferlik kilit açma
    matrix_role_unlocked = Column(Boolean, default=False, nullable=False)

    # limit / usage destek alanları
    last_matrix_deep_analysis = Column(DateTime, nullable=True)

    # hesap silme akışı
    deletion_requested_at = Column(DateTime, nullable=True)
    account_deleted_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)