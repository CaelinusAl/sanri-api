from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.services.auth import decode_token

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryIn(BaseModel):
    type: str
    content: str


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = authorization.replace("Bearer ", "").strip()
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    row = db.execute(
        text("""
            SELECT id, email, name
            FROM users
            WHERE id = :uid
            LIMIT 1
        """),
        {"uid": int(user_id)},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    return row


@router.get("/")
def get_memory(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT id, type, content, created_at
            FROM user_memory
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT 50
        """),
        {"user_id": user["id"]},
    ).mappings().all()

    return [dict(r) for r in rows]


@router.post("/")
def save_memory(
    payload: MemoryIn,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.execute(
        text("""
            INSERT INTO user_memory (user_id, type, content)
            VALUES (:user_id, :type, :content)
        """),
        {
            "user_id": user["id"],
            "type": payload.type,
            "content": payload.content,
        },
    )
    db.commit()

    return {"status": "ok"}


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.execute(
        text("""
            DELETE FROM user_memory
            WHERE id = :id AND user_id = :user_id
        """),
        {
            "id": memory_id,
            "user_id": user["id"],
        },
    )
    db.commit()

    return {"status": "deleted"}