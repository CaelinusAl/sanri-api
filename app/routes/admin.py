# app/routes/admin.py
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db import get_db
from app.models.event import Event
from app.models.memory import Memory

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_TOKEN = (os.getenv("SANRI_ADMIN_TOKEN") or "").strip()

def require_admin(x_admin_token: Optional[str]):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="SANRI_ADMIN_TOKEN missing")
    if not x_admin_token or x_admin_token.strip() != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Admin only")

@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    require_admin(x_admin_token)

    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)

    total_events = db.query(func.count(Event.id)).scalar() or 0
    events_24h = db.query(func.count(Event.id)).filter(Event.created_at >= since_24h).scalar() or 0
    events_7d = db.query(func.count(Event.id)).filter(Event.created_at >= since_7d).scalar() or 0

    top_domains = (
        db.query(Event.domain, func.count(Event.id).label("c"))
        .filter(Event.created_at >= since_7d)
        .group_by(Event.domain)
        .order_by(desc(func.count(Event.id)))
        .limit(10)
        .all()
    )

    last_events = (
        db.query(Event)
        .order_by(desc(Event.created_at))
        .limit(20)
        .all()
    )

    return {
        "now": now.isoformat(),
        "total_events": int(total_events),
        "events_24h": int(events_24h),
        "events_7d": int(events_7d),
        "top_domains": [{"domain": (d or "unknown"), "count": int(c)} for d, c in top_domains],
        "last_events": [
            {
                "id": e.id,
                "user_id": e.user_id,
                "action": e.action,
                "domain": e.domain,
                "meta": e.meta,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in last_events
        ],
    }

@router.get("/events")
def list_events(
    limit: int = 50,
    offset: int = 0,
    domain: Optional[str] = None,
    action: Optional[str] = None,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    require_admin(x_admin_token)

    q = db.query(Event)
    if domain:
        q = q.filter(Event.domain == domain)
    if action:
        q = q.filter(Event.action == action)

    rows = q.order_by(desc(Event.created_at)).offset(offset).limit(min(limit, 200)).all()

    return {
        "items": [
            {
                "id": e.id,
                "user_id": e.user_id,
                "action": e.action,
                "domain": e.domain,
                "meta": e.meta,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in rows
        ],
        "limit": limit,
        "offset": offset,
    }

@router.get("/memories")
def list_memories(
    limit: int = 50,
    offset: int = 0,
    mem_type: Optional[str] = None,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    require_admin(x_admin_token)

    q = db.query(Memory)
    if mem_type:
        q = q.filter(Memory.type == mem_type)

    rows = q.order_by(desc(Memory.created_at)).offset(offset).limit(min(limit, 200)).all()

    return {
        "items": [
            {
                "id": m.id,
                "user_id": m.user_id,
                "type": m.type,
                "context": m.context,
                "input_text": m.input_text,
                "output_text": m.output_text,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ],
        "limit": limit,
        "offset": offset,
    }