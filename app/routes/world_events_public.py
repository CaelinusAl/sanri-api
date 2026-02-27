import os
from typing import Optional, List, Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db import get_db
from app.models.world_event import WorldEvent

router = APIRouter(prefix="/world-events", tags=["world-events"])

@router.get("/list")
def public_list(status: str = "published", limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(WorldEvent).filter(WorldEvent.status == status)
    rows = q.order_by(desc(WorldEvent.is_pinned), desc(WorldEvent.created_at)).limit(min(limit, 200)).all()

    return [
        {
            "id": r.id,
            "title": r.title,
            "source_url": r.source_url,
            "user_note": r.user_note,
            "reading_tr": r.reading_tr,
            "reading_en": r.reading_en,
            "tags": r.tags or [],
            "meta": r.meta or {},
            "status": r.status,
            "is_pinned": bool(r.is_pinned),
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]

@router.get("/pinned")
def pinned(db: Session = Depends(get_db)):
    r = (
        db.query(WorldEvent)
        .filter(WorldEvent.is_pinned == True, WorldEvent.status == "published")
        .order_by(desc(WorldEvent.created_at))
        .first()
    )
    if not r:
        return None

    return {
        "id": r.id,
        "title": r.title,
        "source_url": r.source_url,
        "user_note": r.user_note,
        "reading_tr": r.reading_tr,
        "reading_en": r.reading_en,
        "tags": r.tags or [],
        "meta": r.meta or {},
        "status": r.status,
        "is_pinned": bool(r.is_pinned),
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }