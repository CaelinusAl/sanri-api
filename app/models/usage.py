from datetime import date
from sqlalchemy import Column, Integer, String, Date, UniqueConstraint
from app.db import Base


class Usage(Base):
    __tablename__ = "usage"

    id = Column(Integer, primary_key=True, index=True)

    external_id = Column(String, index=True, nullable=False)
    day = Column(Date, index=True, nullable=False)

    # sayaçlar
    total = Column(Integer, default=0, nullable=False)
    quick_read_count = Column(Integer, default=0, nullable=False)
    ritual_live_count = Column(Integer, default=0, nullable=False)
    city_read_count = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("external_id", "day", name="uq_usage_external_day"),
    )