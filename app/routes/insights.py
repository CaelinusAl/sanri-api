# app/routes/insights.py

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, Dict, Any

from app.db import get_db

router = APIRouter(prefix="/insights", tags=["insights"])


# ----------------------------------------------------
# USER RESOLVE (Bearer token OR X-User-Id fallback)
# ----------------------------------------------------

def get_current_user(
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):

    # -----------------------------
    # Bearer token login
    # -----------------------------

    if authorization and authorization.startswith("Bearer "):

        token = authorization.replace("Bearer ", "").strip()

        row = db.execute(
            text("""
            SELECT id, email, name
            FROM users
            WHERE access_token = :token
            LIMIT 1
            """),
            {"token": token}
        ).mappings().first()

        if row:
            return row


    # -----------------------------
    # X-User-Id fallback
    # -----------------------------

    if x_user_id:

        row = db.execute(
            text("""
            SELECT id, email, name
            FROM users
            WHERE id = :uid
            LIMIT 1
            """),
            {"uid": int(x_user_id)}
        ).mappings().first()

        if row:
            return row


    raise HTTPException(status_code=401, detail="Unauthorized")


# ----------------------------------------------------
# GET USER INSIGHT
# ----------------------------------------------------

@router.get("/")
def get_insight(
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    try:

        row = db.execute(
            text("""
            SELECT theme, focus, symbol, ritual_direction, next_area, raw_json
            FROM user_insights
            WHERE user_id = :uid
            LIMIT 1
            """),
            {"uid": user["id"]}
        ).mappings().first()

        if not row:
            return {
                "theme": "",
                "focus": "",
                "symbol": "",
                "ritual_direction": "",
                "next_area": "",
                "raw_json": ""
            }

        return dict(row)

    except Exception as e:

        return {
            "theme": "",
            "focus": "",
            "symbol": "",
            "ritual_direction": "",
            "next_area": "",
            "raw_json": "",
            "error": str(e)
        }