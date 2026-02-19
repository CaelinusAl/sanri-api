import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Header, HTTPException, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.user_repo import get_or_create_user

router = APIRouter(prefix="/admin", tags=["admin-premium"])

ADMIN_SECRET = (os.getenv("SANRI_ADMIN_SECRET") or "").strip()

@router.post("/grant-premium")
def grant_premium(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_admin_secret: str | None = Header(default=None, alias="X-Admin-Secret"),
    days: int = 30,
    db: Session = Depends(get_db),
):
    if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not x_user_id:
        raise HTTPException(status_code=400, detail="Missing X-User-Id")

    user = get_or_create_user(db, x_user_id)
    user.is_premium = True
    user.premium_until = datetime.utcnow() + timedelta(days=days)
    db.add(user)
    db.commit()

    return {"ok": True, "premium_until": user.premium_until.isoformat()}