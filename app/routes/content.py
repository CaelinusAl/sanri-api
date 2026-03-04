# app/routes/content.py
import os
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.daily_stream import get_or_create_daily

router = APIRouter(prefix="/content", tags=["content"])

def _require_cron_secret(x_cron_token: str | None):
    secret = (os.getenv("CRON_SECRET") or "").strip()
    if not secret:
        return # secret yoksa zorunlu yapmıyoruz (istersen zorunluya çeviririz)
    if (x_cron_token or "").strip() != secret:
        raise HTTPException(status_code=401, detail={"code": "CRON_UNAUTHORIZED"})

@router.get("/daily_stream")
def daily_stream(
    lang: str = "tr",
    x_cron_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    # Eğer cron’dan çağırıyorsan koruyalım
    # mobil de çağırabilir; secret boşsa serbest
    # secret doluysa mobilde header göndermeyeceği için sadece cron kullansın diye
    # şu satırı istersen kapatırız:
    # _require_cron_secret(x_cron_token)

    row = get_or_create_daily(db, lang=lang)
    return {
        "day": str(row.day),
        "lang": row.lang,
        "title": row.title,
        "body": row.body,
        "tags": [t for t in (row.tags or "").split(",") if t],
    }

@router.post("/daily_stream/generate")
def daily_stream_generate(
    lang: str = "tr",
    x_cron_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    # Cron job buradan çağırır (güvenli)
    _require_cron_secret(x_cron_token)
    row = get_or_create_daily(db, lang=lang)
    return {"ok": True, "day": str(row.day), "lang": row.lang}