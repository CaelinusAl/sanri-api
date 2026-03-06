from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db

router = APIRouter()


@router.get("/me")
def get_me(db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT id, name, email
        FROM users
        ORDER BY id DESC
        LIMIT 1
    """)).mappings().first()

    if not row:
        return {
            "name": "Guest",
            "email": "",
            "vip": False
        }

    return {
        "id": row["id"],
        "name": row["name"] or "Guest",
        "email": row["email"] or "",
        "vip": False
    }