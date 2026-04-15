"""
Funnel analytics — event tracking + admin stats for Matrix Rol Okuma funnel.
"""
from typing import Optional, List
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, case, text

from app.db import get_db
from app.models.funnel_event import FunnelEvent
from app.routes.auth import get_current_user
from app.services.auth import decode_token

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
    # Okuma funnel
    "okuma_page_view",
    "okuma_detail_view",
    "okuma_paywall_view",
    "okuma_unlock_click",
    "okuma_shopier_redirect",
    "okuma_unlock_success",
    "okuma_share_click",
    # Kod Egitmeni funnel
    "kod_page_view",
    "kod_module_view",
    "kod_lesson_view",
    "kod_paywall_view",
    "kod_unlock_click",
    "kod_shopier_redirect",
    "kod_unlock_success",
    # Anlasilma funnel
    "anlasilma_page_view",
    "anlasilma_input_submit",
    "anlasilma_result_view",
    "anlasilma_to_frekans",
    "anlasilma_to_yanki",
    "anlasilma_to_okuma",
    # Onboarding quiz funnel
    "landing_view",
    "intro_cta_click",
    "quiz_start",
    "quiz_step_complete",
    "email_submit",
    "quiz_result_view",
    "result_cta_click",
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


def _require_admin(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    payload = decode_token(authorization.replace("Bearer ", "").strip())
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token")
    row = db.execute(
        text("SELECT id, email, role FROM users WHERE id = :uid LIMIT 1"),
        {"uid": int(payload["sub"])},
    ).mappings().first()
    if not row or row["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return dict(row)


@router.get("/admin/stats")
def funnel_stats(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
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

    okuma_funnel = {
        "page_view": counts.get("okuma_page_view", 0),
        "detail_view": counts.get("okuma_detail_view", 0),
        "paywall_view": counts.get("okuma_paywall_view", 0),
        "unlock_click": counts.get("okuma_unlock_click", 0),
        "shopier_redirect": counts.get("okuma_shopier_redirect", 0),
        "unlock_success": counts.get("okuma_unlock_success", 0),
        "share_click": counts.get("okuma_share_click", 0),
    }
    okuma_rates = {
        "view_to_detail": _rate(okuma_funnel["page_view"], okuma_funnel["detail_view"]),
        "detail_to_paywall": _rate(okuma_funnel["detail_view"], okuma_funnel["paywall_view"]),
        "paywall_to_click": _rate(okuma_funnel["paywall_view"], okuma_funnel["unlock_click"]),
        "click_to_shopier": _rate(okuma_funnel["unlock_click"], okuma_funnel["shopier_redirect"]),
        "shopier_to_unlock": _rate(okuma_funnel["shopier_redirect"], okuma_funnel["unlock_success"]),
        "overall": _rate(okuma_funnel["page_view"], okuma_funnel["unlock_success"]),
    }

    kod_funnel = {
        "page_view": counts.get("kod_page_view", 0),
        "module_view": counts.get("kod_module_view", 0),
        "lesson_view": counts.get("kod_lesson_view", 0),
        "paywall_view": counts.get("kod_paywall_view", 0),
        "unlock_click": counts.get("kod_unlock_click", 0),
        "shopier_redirect": counts.get("kod_shopier_redirect", 0),
        "unlock_success": counts.get("kod_unlock_success", 0),
    }
    kod_rates = {
        "view_to_module": _rate(kod_funnel["page_view"], kod_funnel["module_view"]),
        "module_to_lesson": _rate(kod_funnel["module_view"], kod_funnel["lesson_view"]),
        "lesson_to_paywall": _rate(kod_funnel["lesson_view"], kod_funnel["paywall_view"]),
        "paywall_to_click": _rate(kod_funnel["paywall_view"], kod_funnel["unlock_click"]),
        "overall": _rate(kod_funnel["page_view"], kod_funnel["unlock_success"]),
    }

    anlasilma_funnel = {
        "page_view": counts.get("anlasilma_page_view", 0),
        "input_submit": counts.get("anlasilma_input_submit", 0),
        "result_view": counts.get("anlasilma_result_view", 0),
        "to_frekans": counts.get("anlasilma_to_frekans", 0),
        "to_yanki": counts.get("anlasilma_to_yanki", 0),
        "to_okuma": counts.get("anlasilma_to_okuma", 0),
    }
    anlasilma_rates = {
        "view_to_submit": _rate(anlasilma_funnel["page_view"], anlasilma_funnel["input_submit"]),
        "submit_to_result": _rate(anlasilma_funnel["input_submit"], anlasilma_funnel["result_view"]),
        "result_to_action": _rate(
            anlasilma_funnel["result_view"],
            anlasilma_funnel["to_frekans"] + anlasilma_funnel["to_yanki"] + anlasilma_funnel["to_okuma"],
        ),
    }

    return {
        "days": days,
        "role_funnel": role_funnel,
        "role_rates": role_rates,
        "okuma_funnel": okuma_funnel,
        "okuma_rates": okuma_rates,
        "kod_funnel": kod_funnel,
        "kod_rates": kod_rates,
        "anlasilma_funnel": anlasilma_funnel,
        "anlasilma_rates": anlasilma_rates,
        "sources": {r.source or "unknown": r.cnt for r in source_rows},
        "devices": {r.device_type or "unknown": r.cnt for r in device_rows},
        "hourly": {int(r.hr): r.cnt for r in hour_rows},
        "total_events": sum(counts.values()),
    }
