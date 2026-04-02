"""
Funnel analytics — event tracking + admin stats for Matrix Rol Okuma funnel.
"""
from typing import Optional, List
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, case, text

from app.db import get_db
from app.models.funnel_event import FunnelEvent
from app.routes.auth import get_current_user

router = APIRouter(prefix="/funnel", tags=["funnel"])

VALID_EVENTS = {
    "role_page_view",
    "role_form_start",
    "role_form_submit",
    "role_free_result_view",
    "role_lock_view",
    "role_unlock_click",
    "role_shopier_redirect",
    "role_unlock_success",
    "ankod_page_view",
    "ankod_quiz_start",
    "ankod_quiz_complete",
    "ankod_lock_view",
    "ankod_unlock_click",
    "ankod_shopier_redirect",
    "ankod_unlock_success",
}


class EventIn(BaseModel):
    event_type: str
    session_id: Optional[str] = None
    source: Optional[str] = "direct"
    device_type: Optional[str] = "unknown"
    extra: Optional[str] = None


class EventBatchIn(BaseModel):
    events: List[EventIn]


@router.post("/event")
def track_event(body: EventIn, db: Session = Depends(get_db)):
    if body.event_type not in VALID_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unknown event: {body.event_type}")

    ev = FunnelEvent(
        event_type=body.event_type,
        session_id=body.session_id,
        source=body.source,
        device_type=body.device_type,
        extra=body.extra,
    )
    db.add(ev)
    db.commit()
    return {"ok": True}


@router.post("/events")
def track_events_batch(body: EventBatchIn, db: Session = Depends(get_db)):
    added = 0
    for e in body.events:
        if e.event_type not in VALID_EVENTS:
            continue
        ev = FunnelEvent(
            event_type=e.event_type,
            session_id=e.session_id,
            source=e.source,
            device_type=e.device_type,
            extra=e.extra,
        )
        db.add(ev)
        added += 1
    db.commit()
    return {"ok": True, "added": added}


@router.get("/admin/stats")
def funnel_stats(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.query(
            FunnelEvent.event_type,
            func.count(FunnelEvent.id).label("cnt"),
        )
        .filter(FunnelEvent.created_at >= since)
        .group_by(FunnelEvent.event_type)
        .all()
    )

    counts = {r.event_type: r.cnt for r in rows}

    role_funnel = {
        "page_view": counts.get("role_page_view", 0),
        "form_start": counts.get("role_form_start", 0),
        "form_submit": counts.get("role_form_submit", 0),
        "free_result": counts.get("role_free_result_view", 0),
        "lock_view": counts.get("role_lock_view", 0),
        "unlock_click": counts.get("role_unlock_click", 0),
        "shopier_redirect": counts.get("role_shopier_redirect", 0),
        "unlock_success": counts.get("role_unlock_success", 0),
    }

    def _rate(a, b):
        return round((b / a) * 100, 1) if a > 0 else 0.0

    role_rates = {
        "view_to_form": _rate(role_funnel["page_view"], role_funnel["form_start"]),
        "form_to_submit": _rate(role_funnel["form_start"], role_funnel["form_submit"]),
        "submit_to_result": _rate(role_funnel["form_submit"], role_funnel["free_result"]),
        "result_to_lock": _rate(role_funnel["free_result"], role_funnel["lock_view"]),
        "lock_to_click": _rate(role_funnel["lock_view"], role_funnel["unlock_click"]),
        "click_to_shopier": _rate(role_funnel["unlock_click"], role_funnel["shopier_redirect"]),
        "shopier_to_unlock": _rate(role_funnel["shopier_redirect"], role_funnel["unlock_success"]),
        "overall": _rate(role_funnel["page_view"], role_funnel["unlock_success"]),
    }

    source_rows = (
        db.query(
            FunnelEvent.source,
            func.count(FunnelEvent.id).label("cnt"),
        )
        .filter(FunnelEvent.created_at >= since)
        .group_by(FunnelEvent.source)
        .order_by(func.count(FunnelEvent.id).desc())
        .limit(10)
        .all()
    )

    device_rows = (
        db.query(
            FunnelEvent.device_type,
            func.count(FunnelEvent.id).label("cnt"),
        )
        .filter(FunnelEvent.created_at >= since)
        .group_by(FunnelEvent.device_type)
        .all()
    )

    hour_rows = (
        db.query(
            func.extract("hour", FunnelEvent.created_at).label("hr"),
            func.count(FunnelEvent.id).label("cnt"),
        )
        .filter(FunnelEvent.created_at >= since)
        .group_by(text("1"))
        .order_by(text("1"))
        .all()
    )

    return {
        "days": days,
        "role_funnel": role_funnel,
        "role_rates": role_rates,
        "sources": {r.source or "unknown": r.cnt for r in source_rows},
        "devices": {r.device_type or "unknown": r.cnt for r in device_rows},
        "hourly": {int(r.hr): r.cnt for r in hour_rows},
        "total_events": sum(counts.values()),
    }
