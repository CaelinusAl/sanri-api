from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db import get_db

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("")
def get_profile(db: Session = Depends(get_db)):

    row = db.execute(text("""
        SELECT id, name, email, language, bio, intention, vip
        FROM users
        ORDER BY id DESC
        LIMIT 1
    """)).mappings().first()

    if not row:
        return {
            "name": "",
            "email": "",
            "language": "tr",
            "bio": "",
            "intention": "",
            "vip": False
        }

    return dict(row)


@router.post("/update")
def update_profile(data: dict, db: Session = Depends(get_db)):

    db.execute(text("""
        UPDATE users
        SET
            name = :name,
            email = :email,
            language = :language,
            bio = :bio,
            intention = :intention
        WHERE id = (
            SELECT id FROM users
            ORDER BY id DESC
            LIMIT 1
        )
    """), data)

    db.commit()

    return {"status": "ok"}