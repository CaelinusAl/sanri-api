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
                SELECT id, name, email, language, bio, intention, vip
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
                "language": "tr",
                "bio": "",
                "intention": "",
                "vip": False
            }

        return {
            "id": row.get("id"),
            "name": row.get("name") or "Guest",
            "email": row.get("email") or "",
            "language": row.get("language") or "tr",
            "bio": row.get("bio") or "",
            "intention": row.get("intention") or "",
            "vip": bool(row.get("vip") or False)
        }

    except Exception as e:
        return {
            "id": None,
            "name": "Guest",
            "email": "",
            "language": "tr",
            "bio": "",
            "intention": "",
            "vip": False,
            "error": str(e)
        }