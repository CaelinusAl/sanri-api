from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db

router = APIRouter(prefix="/me", tags=["me"])


def get_current_user_id(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> int:
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

    return int(row["id"])


@router.get("")
def get_me(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = authorization.replace("Bearer ", "").strip()

    row = db.execute(
        text("""
            SELECT id, email, name, birthdate
            FROM users
            WHERE access_token = :token
            LIMIT 1
        """),
        {"token": token},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "birthdate": row["birthdate"],
    }