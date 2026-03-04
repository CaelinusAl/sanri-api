# app/routes/system_feed.py
import os
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.system_feed import get_latest_feed, generate_daily_stub

router = APIRouter(prefix="/content", tags=["content"])

@router.get("/system-feed")
def system_feed(limit: int = Query(default=10), db: Session = Depends(get_db)):
    items = get_latest_feed(db, limit=max(1, min(limit, 50)))
    return {
        "items": [
            {
                "id": x.id,
                "created_at": x.created_at,
                "kind": x.kind,
                "title": x.title,
                "subtitle": x.subtitle,
                "body_tr": x.body_tr,
                "body_en": x.body_en,
                "source_url": x.source_url,
                "tags": [t for t in (x.tags or "").split(",") if t],
            }
            for x in items
        ]
    }

@router.post("/system-feed/generate")
def system_feed_generate(
    x_cron_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    secret = (os.getenv("CRON_SECRET") or "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail={"code": "CRON_SECRET_MISSING"})
    if (x_cron_secret or "").strip() != secret:
        raise HTTPException(status_code=401, detail={"code": "CRON_SECRET_INVALID"})

    created = generate_daily_stub(db)
    return {"ok": True, "created_id": created.id}