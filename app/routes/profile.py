from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("")
def get_profile(db: Session = Depends(get_db)):

    try:
        row = db.execute(
            text("""
                SELECT id, name, email, language, bio, intention, vip
                FROM users
                ORDER BY id DESC
                LIMIT 1
            """)
        ).mappings().first()

    except Exception as e:
        return {
            "id": None,
            "name": "",
            "email": "",
            "language": "tr",
            "bio": "",
            "intention": "",
            "vip": False,
            "error": str(e)
        }

    if not row:
        return {
            "id": None,
            "name": "",
            "email": "",
            "language": "tr",
            "bio": "",
            "intention": "",
            "vip": False
        }

    return {
        "id": row.get("id"),
        "name": row.get("name") or "",
        "email": row.get("email") or "",
        "language": row.get("language") or "tr",
        "bio": row.get("bio") or "",
        "intention": row.get("intention") or "",
        "vip": bool(row.get("vip") or False)
    }


@router.post("/update")
def update_profile(data: dict, db: Session = Depends(get_db)):

    try:
        db.execute(
            text("""
                UPDATE users
                SET
                    name = :name,
                    email = :email,
                    language = :language,
                    bio = :bio,
                    intention = :intention
                WHERE id = (
                    SELECT id
                    FROM users
                    ORDER BY id DESC
                    LIMIT 1
                )
            """),
            {
                "name": data.get("name", ""),
                "email": data.get("email", ""),
                "language": data.get("language", "tr"),
                "bio": data.get("bio", ""),
                "intention": data.get("intention", ""),
            },
        )

        db.commit()

    except Exception as e:
        return {"status": "error", "message": str(e)}

    return {"status": "ok"}