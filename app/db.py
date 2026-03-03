# app/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()

# Render'da DATABASE_URL boşsa bile app çökmesin:
# (istersen burada Exception fırlatabilirsin; şimdilik dev mod için güvenli)
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./dev.db"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()