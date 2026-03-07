from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional

from app.db import get_db
from app.services.memory_state_engine import build_memory_state, get_memory_state

router = APIRouter(prefix="/memory-state", tags=["memory-state"])


def get_current_user_id(
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> int:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
        row = db.execute(
            text("""
                SELECT id
                FROM users
                WHERE access_token = :token
                LIMIT 1
            """),
            {"token": token},
        ).mappings().first()
        if row:
            return int(row["id"])

    if x_user_id:
        return int(x_user_id)

    raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/")
def read_memory_state(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return get_memory_state(db, user_id)


@router.post("/refresh")
def refresh_memory_state(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return build_memory_state(db, user_id)