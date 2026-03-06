from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from app.db import get_db

router = APIRouter()

class ProfileUpdate(BaseModel):
    name: str
    bio: str
    intention: str
    language: str

@router.post("/profile/update")
def update_profile(data: ProfileUpdate, db: Session = Depends(get_db)):

    db.execute(
        text("""
        UPDATE users
        SET
            name = :name,
            bio = :bio,
            intention = :intention,
            language = :language
        WHERE id = (
            SELECT id FROM users ORDER BY id DESC LIMIT 1
        )
        """),
        {
            "name": data.name,
            "bio": data.bio,
            "intention": data.intention,
            "language": data.language
        }
    )

    db.commit()

    return {"ok": True}