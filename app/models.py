# app/models.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, func
from .db import Base

class User(Base):
    _tablename_ = "users"  # <-- BU ÇOK ÖNEMLİ (çift underscore)

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(320), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_premium = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)