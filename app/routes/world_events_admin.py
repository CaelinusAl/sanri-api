import os
from typing import Optional, List, Any, Dict
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy import update

from app.db import get_db
from app.models.world_event import WorldEvent

router = APIRouter(prefix="/admin/world-events", tags=["admin-world-events"])

ADMIN_TOKEN = (os.getenv("SANRI_ADMIN_TOKEN") or "").strip()

def require_admin(x_admin_token: Optional[str]):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="SANRI_ADMIN_TOKEN missing")
    if not x_admin_token or x_admin_token.strip() != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Admin only")

class WorldEventCreate(BaseModel):
    title: str
    source_url: Optional[str] = None
    user_note: Optional[str] = None
    reading_tr: str
    reading_en: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    status: str = "draft"
    is_pinned: bool = False

class WorldEventOut(BaseModel):
    id: str
    title: str
    source_url: Optional[str]
    user_note: Optional[str]
    reading_tr: str
    reading_en: Optional[str]
    tags: List[str]
    meta: Dict[str, Any]
    status: str
    is_pinned: bool
    created_at: str

@router.post("/create", response_model=WorldEventOut)
def create_world_event(
    payload: WorldEventCreate,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    require_admin(x_admin_token)

    row = WorldEvent(
        title=payload.title.strip(),
        source_url=(payload.source_url.strip() if payload.source_url else None),
        user_note=(payload.user_note.strip() if payload.user_note else None),
        reading_tr=payload.reading_tr.strip(),
        reading_en=(payload.reading_en.strip() if payload.reading_en else None),
        tags=payload.tags,
        meta=payload.meta,
        status=payload.status,
        is_pinned=payload.is_pinned,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return WorldEventOut(
        id=row.id,
        title=row.title,
        source_url=row.source_url,
        user_note=row.user_note,
        reading_tr=row.reading_tr,
        reading_en=row.reading_en,
        tags=row.tags or [],
        meta=row.meta or {},
        status=row.status,
        is_pinned=row.is_pinned,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )

@router.get("/list", response_model=List[WorldEventOut])
def list_world_events(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    require_admin(x_admin_token)

    q = db.query(WorldEvent)
    if status:
        q = q.filter(WorldEvent.status == status)

    rows = (
        q.order_by(desc(WorldEvent.is_pinned), desc(WorldEvent.created_at))
        .offset(offset)
        .limit(min(limit, 200))
        .all()
    )

    return [
        WorldEventOut(
            id=r.id,
            title=r.title,
            source_url=r.source_url,
            user_note=r.user_note,
            reading_tr=r.reading_tr,
            reading_en=r.reading_en,
            tags=r.tags or [],
            meta=r.meta or {},
            status=r.status,
            is_pinned=r.is_pinned,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]

@router.get("/{event_id}", response_model=WorldEventOut)
def get_world_event(
    event_id: str,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    require_admin(x_admin_token)
    r = db.query(WorldEvent).filter(WorldEvent.id == event_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")

    return WorldEventOut(
        id=r.id,
        title=r.title,
        source_url=r.source_url,
        user_note=r.user_note,
        reading_tr=r.reading_tr,
        reading_en=r.reading_en,
        tags=r.tags or [],
        meta=r.meta or {},
        status=r.status,
        is_pinned=r.is_pinned,
        created_at=r.created_at.isoformat() if r.created_at else "",
    )

@router.delete("/{event_id}")
def delete_world_event(
    event_id: str,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    require_admin(x_admin_token)
    r = db.query(WorldEvent).filter(WorldEvent.id == event_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.post("/pin/{event_id}")
def pin_world_event(
    event_id: str,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    require_admin(x_admin_token)

    # 1) önce tüm pinleri kapat
    db.query(WorldEvent).filter(WorldEvent.is_pinned == True).update({"is_pinned": False})
    db.commit()

    # 2) sonra seçileni pinle
    row = db.query(WorldEvent).filter(WorldEvent.id == event_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")

    row.is_pinned = True
    row.status = "published"  # vitrine alınan yayınlı olsun
    db.commit()
    return {"ok": True, "pinned_id": row.id}


@router.post("/unpin/{event_id}")
def unpin_world_event(
    event_id: str,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    require_admin(x_admin_token)

    row = db.query(WorldEvent).filter(WorldEvent.id == event_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")

    row.is_pinned = False
    db.commit()
    return {"ok": True, "unpinned_id": row.id}