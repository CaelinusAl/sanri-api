from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db

router = APIRouter()


@router.get("/me")
def get_me(db: Session = Depends(get_db)):
    try:
        row = db.execute(
            text("""
                SELECT id, email
                FROM users
                ORDER BY id DESC
                LIMIT 1
            """)
        ).mappings().first()

        if not row:
            return {
                "id": None,
                "name": "Guest",
                "email": "",
                "vip": False
            }

        email = row.get("email") or ""
        guessed_name = email.split("@")[0] if email else "Guest"

        return {
            "id": row.get("id"),
            "name": guessed_name,
            "email": email,
            "vip": False
        }

    except Exception as e:
        return {
            "id": None,
            "name": "Guest",
            "email": "",
            "vip": False,
            "error": str(e)
        }