from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.services.auth import decode_token

router = APIRouter(prefix="/auth", tags=["account"])


def get_current_user_id(authorization: str = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = authorization.replace("Bearer ", "").strip()
    payload = decode_token(token)

    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    return int(payload["sub"])


@router.delete("/account")
def delete_account(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        db.execute(
            text("""
                UPDATE users
                SET account_deleted_at = NOW(),
                    deletion_requested_at = NOW(),
                    is_active = FALSE,
                    email = NULL
                WHERE id = :uid
            """),
            {"uid": user_id},
        )
        db.commit()

        return {"success": True, "message": "Account deleted"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
