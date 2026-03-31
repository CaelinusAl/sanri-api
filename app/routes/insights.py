# app/routes/insights.py

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.services.auth import decode_token

router = APIRouter(prefix="/insights", tags=["insights"])


# --------------------------------------------------
# USER RESOLVE
# Bearer token -> decode JWT -> get user_id -> fetch user
# X-User-Id -> sadece fallback/dev için
# --------------------------------------------------
def get_current_user(
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    # 1) JWT Bearer token
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()

        try:
            payload = decode_token(token)
            user_id = payload.get("sub") or payload.get("user_id")

            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid token")

            row = db.execute(
                text(
                    """
                    SELECT id, email, name
                    FROM users
                    WHERE id = :uid
                    LIMIT 1
                    """
                ),
                {"uid": int(user_id)},
            ).mappings().first()

            if row:
                return row

        except Exception:
            raise HTTPException(status_code=401, detail="Token error")

    # 2) Fallback / dev mode
    if x_user_id:
        row = db.execute(
            text(
                """
                SELECT id, email, name
                FROM users
                WHERE id = :uid
                LIMIT 1
                """
            ),
            {"uid": int(x_user_id)},
        ).mappings().first()

        if row:
            return row

    raise HTTPException(status_code=401, detail="Unauthorized")


# --------------------------------------------------
# GET USER INSIGHT
# --------------------------------------------------
@router.get("/")
def get_insight(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = db.execute(
            text(
                """
                SELECT theme, focus, symbol, ritual_direction, next_area, raw_json
                FROM user_insights
                WHERE user_id = :uid
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"uid": user["id"]},
        ).mappings().first()

        if not row:
            return {
                "theme": "Yumuşama",
                "focus": f'{user["name"] or "Seeker"}, bugün bastırdığın bir his çözülmek isteyebilir.',
                "symbol": "Su",
                "ritual_direction": "Bugün tepki vermeden önce 3 derin nefes al.",
                "next_area": "Hafızanda bir cümle bırak.",
                "raw_json": None,
            }

        return dict(row)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insight error: {str(e)}")