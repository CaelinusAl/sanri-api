from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from sqlalchemy import text

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
        "name": row["name"],
        "email": row["email"],
        "vip": False
    }