import os
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.daily_feeling_service import get_today_feeling, generate_daily_feeling

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/daily-feeling")
def daily_feeling(db: Session = Depends(get_db)):
    """Public endpoint — returns today's collective feeling."""
    return get_today_feeling(db)


@router.post("/daily-feeling/generate")
def daily_feeling_generate(
    x_cron_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Cron/admin endpoint — triggers generation for current period."""
    secret = (os.getenv("CRON_SECRET") or "").strip()
    if secret and (x_cron_secret or "").strip() != secret:
        raise HTTPException(status_code=401, detail="CRON_UNAUTHORIZED")
    return generate_daily_feeling(db)
