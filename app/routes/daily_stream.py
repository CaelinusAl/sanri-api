# app/routes/daily_stream.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.daily_stream import get_or_create_daily, get_or_create_weekly

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/daily-stream")
def daily_stream(
    lang: str = Query(default="tr"),
    db: Session = Depends(get_db),
):
    lang = (lang or "tr").lower()
    if lang not in ("tr", "en"):
        lang = "tr"
    return get_or_create_daily(db, lang)


@router.get("/weekly-symbol")
def weekly_symbol(
    lang: str = Query(default="tr"),
    db: Session = Depends(get_db),
):
    lang = (lang or "tr").lower()
    if lang not in ("tr", "en"):
        lang = "tr"
    return get_or_create_weekly(db, lang)