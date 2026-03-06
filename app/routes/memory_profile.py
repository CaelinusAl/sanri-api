from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db

router = APIRouter(prefix="/memory", tags=["memory"])


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = authorization.replace("Bearer ", "").strip()

    row = db.execute(
        text("""
            SELECT id, email, name
            FROM users
            WHERE access_token = :token
            LIMIT 1
        """),
        {"token": token},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid token")

    return row


class MemoryIn(BaseModel):
    memory_key: str
    memory_value: str


@router.get("")
def list_memory(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT id, memory_key, memory_value, created_at, updated_at
            FROM user_memory
            WHERE user_id = :user_id
            ORDER BY updated_at DESC, id DESC
        """),
        {"user_id": user["id"]},
    ).mappings().all()

    return [dict(r) for r in rows]


@router.post("")
def save_memory(
    payload: MemoryIn,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.execute(
        text("""
            INSERT INTO user_memory (user_id, memory_key, memory_value)
            VALUES (:user_id, :memory_key, :memory_value)
            ON CONFLICT (user_id, memory_key)
            DO UPDATE SET
                memory_value = EXCLUDED.memory_value,
                updated_at = now()
        """),
        {
            "user_id": user["id"],
            "memory_key": payload.memory_key.strip(),
            "memory_value": payload.memory_value.strip(),
        },
    )
    db.commit()

    return {"ok": True}


@router.delete("/{memory_key}")
def delete_memory(
    memory_key: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.execute(
        text("""
            DELETE FROM user_memory
            WHERE user_id = :user_id
              AND memory_key = :memory_key
        """),
        {
            "user_id": user["id"],
            "memory_key": memory_key,
        },
    )
    db.commit()

    return {"ok": True}