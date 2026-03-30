# app/routes/admin.py
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text as sa_text

from app.db import get_db
from app.models.event import Event
from app.models.memory import Memory
from app.services.auth import decode_token

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_TOKEN = (os.getenv("SANRI_ADMIN_TOKEN") or "").strip()


def require_admin(x_admin_token: Optional[str]):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="SANRI_ADMIN_TOKEN missing")
    if not x_admin_token or x_admin_token.strip() != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Admin only")


def _require_admin_jwt(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """JWT-based admin auth for web dashboard."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.replace("Bearer ", "").strip()
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.execute(
        sa_text("SELECT id, email, role FROM users WHERE id = :uid LIMIT 1"),
        {"uid": int(user_id)},
    ).mappings().first()
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return dict(user)

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


# =================================================================
# JWT-BASED WEB ADMIN ENDPOINTS
# =================================================================


@router.get("/dashboard")
def dashboard(
    admin=Depends(_require_admin_jwt),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    total_users = db.execute(sa_text("SELECT COUNT(*) FROM users")).scalar() or 0
    premium_users = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE is_premium = TRUE")).scalar() or 0
    admin_users = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE role = 'admin'")).scalar() or 0
    verified_users = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE email_verified = TRUE")).scalar() or 0
    new_24h = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE created_at >= :s"), {"s": since_24h}).scalar() or 0
    new_7d = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE created_at >= :s"), {"s": since_7d}).scalar() or 0

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

    top_actions = (
        db.query(Event.action, func.count(Event.id).label("c"))
        .filter(Event.created_at >= since_7d)
        .group_by(Event.action)
        .order_by(desc(func.count(Event.id)))
        .limit(10)
        .all()
    )

    last_events = (
        db.query(Event).order_by(desc(Event.created_at)).limit(15).all()
    )

    yanki = {"pending": 0, "published": 0, "rejected": 0}
    try:
        for st in ["pending_review", "published", "rejected"]:
            key = "pending" if st == "pending_review" else st
            yanki[key] = db.execute(
                sa_text("SELECT COUNT(*) FROM yanki_posts WHERE status = :s"), {"s": st}
            ).scalar() or 0
    except Exception:
        pass

    total_memories = 0
    try:
        total_memories = db.query(func.count(Memory.id)).scalar() or 0
    except Exception:
        pass

    return {
        "users": {
            "total": int(total_users),
            "premium": int(premium_users),
            "admin": int(admin_users),
            "verified": int(verified_users),
            "new_24h": int(new_24h),
            "new_7d": int(new_7d),
        },
        "events": {
            "total": int(total_events),
            "last_24h": int(events_24h),
            "last_7d": int(events_7d),
            "top_domains": [{"name": d or "unknown", "count": int(c)} for d, c in top_domains],
            "top_actions": [{"name": a, "count": int(c)} for a, c in top_actions],
        },
        "yanki": yanki,
        "memories": {"total": int(total_memories)},
        "recent_events": [
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


@router.get("/users-list")
def users_list(
    search: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    admin=Depends(_require_admin_jwt),
    db: Session = Depends(get_db),
):
    conditions = []
    params: dict = {"lim": min(limit, 200), "off": offset}

    if search:
        conditions.append("email ILIKE :search")
        params["search"] = f"%{search}%"
    if role:
        conditions.append("role = :role")
        params["role"] = role

    where = " AND ".join(conditions) if conditions else "1=1"

    rows = db.execute(
        sa_text(f"""
            SELECT id, email, role, is_premium, email_verified, created_at
            FROM users
            WHERE {where}
            ORDER BY created_at DESC
            OFFSET :off LIMIT :lim
        """),
        params,
    ).mappings().all()

    total = db.execute(
        sa_text(f"SELECT COUNT(*) FROM users WHERE {where}"),
        {k: v for k, v in params.items() if k not in ("lim", "off")},
    ).scalar() or 0

    return {
        "items": [
            {
                "id": u["id"],
                "email": u["email"],
                "role": u.get("role", "free"),
                "is_premium": bool(u.get("is_premium", False)),
                "email_verified": bool(u.get("email_verified", False)),
                "created_at": str(u["created_at"]) if u.get("created_at") else None,
            }
            for u in rows
        ],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


class SetRoleBody(BaseModel):
    target_user_id: int
    role: str


@router.post("/set-user-role")
def set_user_role(
    payload: SetRoleBody,
    admin=Depends(_require_admin_jwt),
    db: Session = Depends(get_db),
):
    db.execute(
        sa_text("UPDATE users SET role = :role WHERE id = :uid"),
        {"role": payload.role, "uid": payload.target_user_id},
    )
    db.commit()
    return {"ok": True, "user_id": payload.target_user_id, "role": payload.role}


@router.get("/events-list")
def events_list_jwt(
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    domain: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    admin=Depends(_require_admin_jwt),
    db: Session = Depends(get_db),
):
    q = db.query(Event)
    if domain:
        q = q.filter(Event.domain == domain)
    if action:
        q = q.filter(Event.action == action)

    total = q.count()
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
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/memories-list")
def memories_list_jwt(
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    mem_type: Optional[str] = Query(default=None),
    admin=Depends(_require_admin_jwt),
    db: Session = Depends(get_db),
):
    q = db.query(Memory)
    if mem_type:
        q = q.filter(Memory.type == mem_type)

    total = q.count()
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
        "total": total,
        "limit": limit,
        "offset": offset,
    }