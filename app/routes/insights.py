from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db

router = APIRouter(prefix="/insights", tags=["insights"])


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


class InsightIn(BaseModel):
    theme: str = ""
    focus: str = ""
    symbol: str = ""
    ritual_direction: str = ""
    next_area: str = ""
    raw_json: str = ""


@router.get("")
def get_insight(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text("""
            SELECT theme, focus, symbol, ritual_direction, next_area, raw_json, updated_at
            FROM user_insights
            WHERE user_id = :user_id
            LIMIT 1
        """),
        {"user_id": user["id"]},
    ).mappings().first()

    if not row:
        return {
            "theme": "",
            "focus": "",
            "symbol": "",
            "ritual_direction": "",
            "next_area": "",
            "raw_json": "",
        }

    return dict(row)


@router.post("")
def save_insight(
    payload: InsightIn,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.execute(
        text("""
            INSERT INTO user_insights
            (user_id, theme, focus, symbol, ritual_direction, next_area, raw_json)
            VALUES
            (:user_id, :theme, :focus, :symbol, :ritual_direction, :next_area, :raw_json)
            ON CONFLICT (user_id)
            DO UPDATE SET
                theme = EXCLUDED.theme,
                focus = EXCLUDED.focus,
                symbol = EXCLUDED.symbol,
                ritual_direction = EXCLUDED.ritual_direction,
                next_area = EXCLUDED.next_area,
                raw_json = EXCLUDED.raw_json,
                updated_at = now()
        """),
        {
            "user_id": user["id"],
            "theme": payload.theme.strip(),
            "focus": payload.focus.strip(),
            "symbol": payload.symbol.strip(),
            "ritual_direction": payload.ritual_direction.strip(),
            "next_area": payload.next_area.strip(),
            "raw_json": payload.raw_json.strip(),
        },
    )
    db.commit()

    return {"ok": True}