from datetime import datetime, timedelta
from fastapi import APIRouter, Header, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.user_repo import get_or_create_user

router = APIRouter(prefix="/premium", tags=["premium"])

@router.get("/status")
def premium_status(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-Id")
    user = get_or_create_user(db, x_user_id)

    days_left = None
    if user.last_matrix_deep_analysis:
        next_allowed = user.last_matrix_deep_analysis + timedelta(days=30)
        now = datetime.utcnow()
        if now < next_allowed:
            days_left = max(0, (next_allowed - now).days)
        else:
            days_left = 0

    return {
        "is_premium": bool(user.is_premium),
        "days_left": days_left, # None | 0..30
    }