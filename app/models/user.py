from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # X-User-Id (device id) ile bağlayacağız
    external_id = Column(String, unique=True, index=True, nullable=False)

    # self-only kontrolü için
    name = Column(String, nullable=True)
    birth_date = Column(String, nullable=True) # "21.06.1989" gibi

    # premium
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime, nullable=True)

    # 30 gün kuralı
    last_matrix_deep_analysis = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)