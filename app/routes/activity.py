from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from app.db import get_db

router = APIRouter()


class MemoryIn(BaseModel):
    user_id: int
    type: str
    content: str


@router.get("/memory/{user_id}")
def get_memory(user_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
        SELECT id, user_id, type, content, created_at
        FROM user_memory
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT 50
        """),
        {"user_id": user_id}
    ).mappings().all()

    return [dict(r) for r in rows]


@router.post("/memory")
def save_memory(payload: MemoryIn, db: Session = Depends(get_db)):
    db.execute(
        text("""
        INSERT INTO user_memory (user_id, type, content)
        VALUES (:user_id, :type, :content)
        """),
        {
            "user_id": payload.user_id,
            "type": payload.type,
            "content": payload.content
        }
    )
    db.commit()

    return {"ok": True}