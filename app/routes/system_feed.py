# app/routes/system_feed.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.system_feed import get_latest_feed, generate_and_store_feed

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/system-feed")
def system_feed(lang: str = Query(default="tr"), db: Session = Depends(get_db)):
    lang = (lang or "tr").lower()
    if lang not in ("tr", "en"):
        lang = "tr"
    return get_latest_feed(db, lang)


# Mobil/tarayıcıda kolay test için GET de bırakıyorum
@router.get("/system-feed/generate")
def system_feed_generate_get(lang: str = Query(default="tr"), db: Session = Depends(get_db)):
    lang = (lang or "tr").lower()
    if lang not in ("tr", "en"):
        lang = "tr"
    return generate_and_store_feed(db, lang)


@router.post("/system-feed/generate")
def system_feed_generate_post(lang: str = Query(default="tr"), db: Session = Depends(get_db)):
    lang = (lang or "tr").lower()
    if lang not in ("tr", "en"):
        lang = "tr"
    return generate_and_store_feed(db, lang)