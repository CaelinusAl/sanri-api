# app/models/usage.py
from datetime import date
from sqlalchemy import Column, Integer, String, Date, UniqueConstraint
from app.db import Base

class Usage(Base):
    _tablename_ = "usage"

    id = Column(Integer, primary_key=True, index=True)

    # user external id (device id)
    external_id = Column(String, index=True, nullable=False)

    # yyyy-mm-dd (UTC date)
    day = Column(Date, index=True, nullable=False)

    # counters
    total = Column(Integer, default=0, nullable=False)

    _table_args_ = (
        UniqueConstraint("external_id", "day", name="uq_usage_external_day"),
    )