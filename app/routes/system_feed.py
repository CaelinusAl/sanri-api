# app/routes/system_feed.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.system_feed import get_latest_feed

router = APIRouter(prefix="/content", tags=["content"])

@router.get("/system-feed")
def system_feed(lang: str = Query(default="tr"), db: Session = Depends(get_db)):
    return get_latest_feed(db, lang)