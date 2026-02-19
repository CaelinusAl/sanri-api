from datetime import datetime
from sqlalchemy import Column, DateTime, Boolean

is_premium = Column(Boolean, default=False)
last_matrix_deep_analysis = Column(DateTime, nullable=True)