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
                SELECT id, name, email
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

        return {
            "id": row.get("id"),
            "name": row.get("name") or "Guest",
            "email": row.get("email") or "",
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