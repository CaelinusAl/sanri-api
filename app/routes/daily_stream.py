# app/routes/daily_stream.py
import os
from fastapi import APIRouter, Depends, Query, HTTPException, Header
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.daily_stream import get_or_create_daily, get_or_create_weekly

router = APIRouter(prefix="/content", tags=["content"])

def _norm_lang(lang: str) -> str:
    lang = (lang or "tr").lower().strip()
    return lang if lang in ("tr", "en") else "tr"

@router.get("/daily-stream")
def daily_stream(lang: str = Query(default="tr"), db: Session = Depends(get_db)):
    lang = _norm_lang(lang)
    return get_or_create_daily(db, lang)

@router.get("/weekly-symbol")
def weekly_symbol(lang: str = Query(default="tr"), db: Session = Depends(get_db)):
    lang = _norm_lang(lang)
    return get_or_create_weekly(db, lang)

@router.post("/cron/run")
def cron_run(
    db: Session = Depends(get_db),
    x_cron_secret: str | None = Header(default=None),
):
    secret = (os.getenv("CRON_SECRET") or "").strip()
    if secret and x_cron_secret != secret:
        raise HTTPException(status_code=401, detail={"code": "CRON_UNAUTHORIZED"})

    out = {
        "daily_tr": get_or_create_daily(db, "tr"),
        "daily_en": get_or_create_daily(db, "en"),
        "weekly_tr": get_or_create_weekly(db, "tr"),
        "weekly_en": get_or_create_weekly(db, "en"),
    }
    return {"ok": True, "generated": True, "data": out}