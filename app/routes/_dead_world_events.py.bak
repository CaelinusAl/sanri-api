from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db import get_db
from app.models.world_event import WorldEvent

router = APIRouter(prefix="/world-events", tags=["world-events"])


@router.get("/list")
def list_world_events(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(WorldEvent)
        .filter(WorldEvent.status == "published")
        .order_by(desc(WorldEvent.is_pinned), desc(WorldEvent.created_at))
        .limit(limit)
        .all()
    )

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
            "is_pinned": r.is_pinned,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]


@router.get("/pinned")
def pinned_world_event(db: Session = Depends(get_db)):
    row = (
        db.query(WorldEvent)
        .filter(WorldEvent.is_pinned == True)
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail="No pinned event")

    return {
        "id": row.id,
        "title": row.title,
        "source_url": row.source_url,
        "user_note": row.user_note,
        "reading_tr": row.reading_tr,
        "reading_en": row.reading_en,
        "tags": row.tags or [],
        "meta": row.meta or {},
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }