# app/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

def _normalize_db_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    # SQLAlchemy "postgres://" sevmez
    if u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://"):]
    return u

DATABASE_URL = _normalize_db_url(os.getenv("DATABASE_URL") or "")

# Render'da DB bazen yok / geç açılır → servis çökmesin
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./dev.db"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()