# app/routes/admin.py  —  Sanri Control Tower API
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text as sa_text

from app.db import get_db, engine
from app.models.event import Event
from app.models.memory import Memory
from app.services.auth import decode_token

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_TOKEN = (os.getenv("SANRI_ADMIN_TOKEN") or "").strip()


# ═══════════════════════════════════════════════
# TABLES
# ═══════════════════════════════════════════════

def _ensure_admin_tables():
    with engine.connect() as conn:
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id SERIAL PRIMARY KEY,
                admin_id INTEGER NOT NULL,
                admin_email VARCHAR(255),
                action VARCHAR(100) NOT NULL,
                target_type VARCHAR(50),
                target_id VARCHAR(100),
                details JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()


try:
    _ensure_admin_tables()
except Exception as e:
    print(f"[ADMIN] Table migration: {e}")


# ═══════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════

def _require_legacy(x_admin_token: Optional[str]):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="SANRI_ADMIN_TOKEN not set")
    if not x_admin_token or x_admin_token.strip() != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Admin only")


def _require_jwt(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.replace("Bearer ", "").strip()
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Bad token")
    row = db.execute(
        sa_text("SELECT id, email, role FROM users WHERE id = :uid LIMIT 1"),
        {"uid": int(uid)},
    ).mappings().first()
    if not row or row["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return dict(row)


# ═══════════════════════════════════════════════
# AUDIT
# ═══════════════════════════════════════════════

def _audit(db, admin, action, target_type=None, target_id=None, details=None):
    try:
        db.execute(sa_text("""
            INSERT INTO admin_audit_log
                (admin_id, admin_email, action, target_type, target_id, details)
            VALUES (:aid, :ae, :act, :tt, :tid, :det::jsonb)
        """), {
            "aid": admin["id"],
            "ae": admin["email"],
            "act": action,
            "tt": target_type,
            "tid": str(target_id) if target_id else None,
            "det": json.dumps(details) if details else None,
        })
        db.commit()
    except Exception as e:
        print(f"[AUDIT] {e}")


# ═══════════════════════════════════════════════
# LEGACY ENDPOINTS  (X-Admin-Token — backward compat)
# ═══════════════════════════════════════════════

@router.get("/overview")
def overview(db: Session = Depends(get_db), x_admin_token: Optional[str] = Header(default=None)):
    _require_legacy(x_admin_token)
    now = datetime.now(timezone.utc)
    s24 = now - timedelta(hours=24)
    s7d = now - timedelta(days=7)
    total = db.query(func.count(Event.id)).scalar() or 0
    e24 = db.query(func.count(Event.id)).filter(Event.created_at >= s24).scalar() or 0
    e7d = db.query(func.count(Event.id)).filter(Event.created_at >= s7d).scalar() or 0
    td = db.query(Event.domain, func.count(Event.id).label("c")).filter(Event.created_at >= s7d).group_by(Event.domain).order_by(desc(func.count(Event.id))).limit(10).all()
    last = db.query(Event).order_by(desc(Event.created_at)).limit(20).all()
    return {
        "total_events": int(total), "events_24h": int(e24), "events_7d": int(e7d),
        "top_domains": [{"domain": d or "unknown", "count": int(c)} for d, c in td],
        "last_events": [{"id": e.id, "user_id": e.user_id, "action": e.action, "domain": e.domain, "meta": e.meta, "created_at": e.created_at.isoformat() if e.created_at else None} for e in last],
    }


@router.get("/events")
def legacy_events(limit: int = 50, offset: int = 0, domain: Optional[str] = None, action: Optional[str] = None, db: Session = Depends(get_db), x_admin_token: Optional[str] = Header(default=None)):
    _require_legacy(x_admin_token)
    q = db.query(Event)
    if domain: q = q.filter(Event.domain == domain)
    if action: q = q.filter(Event.action == action)
    rows = q.order_by(desc(Event.created_at)).offset(offset).limit(min(limit, 200)).all()
    return {"items": [{"id": e.id, "user_id": e.user_id, "action": e.action, "domain": e.domain, "meta": e.meta, "created_at": e.created_at.isoformat() if e.created_at else None} for e in rows]}


@router.get("/memories")
def legacy_memories(limit: int = 50, offset: int = 0, mem_type: Optional[str] = None, db: Session = Depends(get_db), x_admin_token: Optional[str] = Header(default=None)):
    _require_legacy(x_admin_token)
    q = db.query(Memory)
    if mem_type: q = q.filter(Memory.type == mem_type)
    rows = q.order_by(desc(Memory.created_at)).offset(offset).limit(min(limit, 200)).all()
    return {"items": [{"id": m.id, "user_id": m.user_id, "type": m.type, "context": m.context, "input_text": m.input_text, "output_text": m.output_text, "created_at": m.created_at.isoformat() if m.created_at else None} for m in rows]}


# ═══════════════════════════════════════════════
# CONTROL TOWER — DASHBOARD
# ═══════════════════════════════════════════════

@router.get("/dashboard")
def dashboard(admin=Depends(_require_jwt), db: Session = Depends(get_db)):
    _audit(db, admin, "view_dashboard")
    now = datetime.now(timezone.utc)
    s24 = now - timedelta(hours=24)
    s7d = now - timedelta(days=7)

    total_u = db.execute(sa_text("SELECT COUNT(*) FROM users")).scalar() or 0
    premium = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE is_premium = TRUE")).scalar() or 0
    admins = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE role = 'admin'")).scalar() or 0
    verified = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE email_verified = TRUE")).scalar() or 0
    new24 = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE created_at >= :s"), {"s": s24}).scalar() or 0
    new7d = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE created_at >= :s"), {"s": s7d}).scalar() or 0
    active24 = db.execute(sa_text("SELECT COUNT(DISTINCT user_id) FROM events WHERE created_at >= :s AND user_id IS NOT NULL"), {"s": s24}).scalar() or 0

    total_ev = db.query(func.count(Event.id)).scalar() or 0
    ev24 = db.query(func.count(Event.id)).filter(Event.created_at >= s24).scalar() or 0
    ev7d = db.query(func.count(Event.id)).filter(Event.created_at >= s7d).scalar() or 0
    vip_c = db.query(func.count(Event.id)).filter(Event.action == "vip_click", Event.created_at >= s7d).scalar() or 0
    vip_u = db.query(func.count(Event.id)).filter(Event.action == "vip_unlock", Event.created_at >= s7d).scalar() or 0

    td = db.query(Event.domain, func.count(Event.id).label("c")).filter(Event.created_at >= s7d).group_by(Event.domain).order_by(desc(func.count(Event.id))).limit(10).all()
    ta = db.query(Event.action, func.count(Event.id).label("c")).filter(Event.created_at >= s7d).group_by(Event.action).order_by(desc(func.count(Event.id))).limit(10).all()
    last = db.query(Event).order_by(desc(Event.created_at)).limit(20).all()

    yk = {"pending": 0, "published": 0, "rejected": 0}
    try:
        for st in ["pending_review", "published", "rejected"]:
            key = "pending" if st == "pending_review" else st
            yk[key] = db.execute(sa_text("SELECT COUNT(*) FROM yanki_posts WHERE status = :s"), {"s": st}).scalar() or 0
    except Exception:
        pass

    mem = 0
    try:
        mem = db.query(func.count(Memory.id)).scalar() or 0
    except Exception:
        pass

    return {
        "users": {"total": int(total_u), "premium": int(premium), "admin": int(admins), "verified": int(verified), "active_24h": int(active24), "new_24h": int(new24), "new_7d": int(new7d)},
        "events": {
            "total": int(total_ev), "last_24h": int(ev24), "last_7d": int(ev7d),
            "vip_clicks": int(vip_c), "vip_unlocks": int(vip_u),
            "top_domains": [{"name": d or "unknown", "count": int(c)} for d, c in td],
            "top_actions": [{"name": a, "count": int(c)} for a, c in ta],
        },
        "yanki": yk,
        "memories": {"total": int(mem)},
        "recent_events": [{"id": e.id, "user_id": e.user_id, "action": e.action, "domain": e.domain, "meta": e.meta, "created_at": e.created_at.isoformat() if e.created_at else None} for e in last],
    }


# ═══════════════════════════════════════════════
# CONTROL TOWER — USERS
# ═══════════════════════════════════════════════

@router.get("/users-list")
def users_list(
    search: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    conds, params = [], {"lim": min(limit, 200), "off": offset}
    if search:
        conds.append("email ILIKE :search")
        params["search"] = f"%{search}%"
    if role:
        conds.append("role = :role")
        params["role"] = role
    w = " AND ".join(conds) if conds else "1=1"

    rows = db.execute(sa_text(f"SELECT id, email, role, is_premium, email_verified, created_at FROM users WHERE {w} ORDER BY created_at DESC OFFSET :off LIMIT :lim"), params).mappings().all()
    total = db.execute(sa_text(f"SELECT COUNT(*) FROM users WHERE {w}"), {k: v for k, v in params.items() if k not in ("lim", "off")}).scalar() or 0

    return {
        "items": [{"id": u["id"], "email": u["email"], "role": u.get("role", "free"), "is_premium": bool(u.get("is_premium")), "email_verified": bool(u.get("email_verified")), "created_at": str(u["created_at"]) if u.get("created_at") else None} for u in rows],
        "total": int(total),
    }


class SetRoleBody(BaseModel):
    target_user_id: int
    role: str


@router.post("/set-user-role")
def set_user_role(payload: SetRoleBody, admin=Depends(_require_jwt), db: Session = Depends(get_db)):
    _audit(db, admin, "set_user_role", "user", payload.target_user_id, {"new_role": payload.role})
    db.execute(sa_text("UPDATE users SET role = :role WHERE id = :uid"), {"role": payload.role, "uid": payload.target_user_id})
    db.commit()
    return {"ok": True, "user_id": payload.target_user_id, "role": payload.role}


# ═══════════════════════════════════════════════
# CONTROL TOWER — ANALYTICS
# ═══════════════════════════════════════════════

@router.get("/analytics")
def analytics(
    period: str = Query(default="7d"),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 7)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    daily_ev = db.execute(sa_text("SELECT DATE(created_at) as day, COUNT(*) as cnt FROM events WHERE created_at >= :s GROUP BY DATE(created_at) ORDER BY day"), {"s": since}).mappings().all()
    daily_usr = db.execute(sa_text("SELECT DATE(created_at) as day, COUNT(*) as cnt FROM users WHERE created_at >= :s GROUP BY DATE(created_at) ORDER BY day"), {"s": since}).mappings().all()
    by_action = db.execute(sa_text("SELECT action, COUNT(*) as cnt FROM events WHERE created_at >= :s GROUP BY action ORDER BY cnt DESC LIMIT 20"), {"s": since}).mappings().all()
    by_domain = db.execute(sa_text("SELECT COALESCE(domain,'unknown') as domain, COUNT(*) as cnt FROM events WHERE created_at >= :s GROUP BY domain ORDER BY cnt DESC LIMIT 20"), {"s": since}).mappings().all()

    counts = {}
    for ev in ["page_view", "mode_switch", "city_open", "vip_click", "vip_unlock", "message_sent", "post_submitted", "purchase_attempt", "purchase_success"]:
        counts[ev] = db.execute(sa_text("SELECT COUNT(*) FROM events WHERE action = :a AND created_at >= :s"), {"a": ev, "s": since}).scalar() or 0

    return {
        "daily_events": [{"day": str(d["day"]), "count": int(d["cnt"])} for d in daily_ev],
        "daily_users": [{"day": str(d["day"]), "count": int(d["cnt"])} for d in daily_usr],
        "by_action": [{"name": d["action"], "count": int(d["cnt"])} for d in by_action],
        "by_domain": [{"name": d["domain"], "count": int(d["cnt"])} for d in by_domain],
        "event_counts": counts,
    }


# ═══════════════════════════════════════════════
# CONTROL TOWER — CONTENT MODERATION
# ═══════════════════════════════════════════════

@router.get("/moderation/posts")
def mod_posts(
    status: Optional[str] = Query(default="pending_review"),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    conds, p = ["1=1"], {"lim": min(limit, 200), "off": offset}
    if status:
        conds.append("status = :status")
        p["status"] = status
    w = " AND ".join(conds)
    try:
        rows = db.execute(sa_text(f"SELECT * FROM yanki_posts WHERE {w} ORDER BY created_at DESC OFFSET :off LIMIT :lim"), p).mappings().all()
        total = db.execute(sa_text(f"SELECT COUNT(*) FROM yanki_posts WHERE {w}"), {k: v for k, v in p.items() if k not in ("lim", "off")}).scalar() or 0
    except Exception:
        rows, total = [], 0
    return {"items": [dict(r) for r in rows], "total": int(total)}


@router.get("/moderation/stats")
def mod_stats(admin=Depends(_require_jwt), db: Session = Depends(get_db)):
    out = {"pending": 0, "published": 0, "rejected": 0, "total_reactions": 0, "total_reports": 0}
    try:
        for st in ["pending_review", "published", "rejected"]:
            key = "pending" if st == "pending_review" else st
            out[key] = db.execute(sa_text("SELECT COUNT(*) FROM yanki_posts WHERE status = :s"), {"s": st}).scalar() or 0
        out["total_reactions"] = db.execute(sa_text("SELECT COALESCE(SUM(reaction_heart + reaction_felt), 0) FROM yanki_posts")).scalar() or 0
        out["total_reports"] = db.execute(sa_text("SELECT COALESCE(SUM(report_count), 0) FROM yanki_posts")).scalar() or 0
    except Exception:
        pass
    return out


class ReviewBody(BaseModel):
    action: str
    sanri_note: Optional[str] = None
    reject_reason: Optional[str] = None


@router.post("/moderation/posts/{post_id}/review")
def review_post(post_id: int, payload: ReviewBody, admin=Depends(_require_jwt), db: Session = Depends(get_db)):
    _audit(db, admin, f"moderation_{payload.action}", "yanki_post", post_id, {"note": payload.sanri_note, "reason": payload.reject_reason})
    if payload.action == "approve":
        db.execute(sa_text("UPDATE yanki_posts SET status = 'published', sanri_note = :n, reviewed_at = NOW(), published_at = NOW() WHERE id = :id"), {"n": payload.sanri_note, "id": post_id})
    elif payload.action == "reject":
        db.execute(sa_text("UPDATE yanki_posts SET status = 'rejected', reject_reason = :r, reviewed_at = NOW() WHERE id = :id"), {"r": payload.reject_reason, "id": post_id})
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════
# CONTROL TOWER — SECURITY CENTER
# ═══════════════════════════════════════════════

@router.get("/security/audit-log")
def audit_log(
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    try:
        rows = db.execute(sa_text("SELECT * FROM admin_audit_log ORDER BY created_at DESC OFFSET :off LIMIT :lim"), {"off": offset, "lim": min(limit, 200)}).mappings().all()
        total = db.execute(sa_text("SELECT COUNT(*) FROM admin_audit_log")).scalar() or 0
    except Exception:
        rows, total = [], 0
    return {
        "items": [{"id": r["id"], "admin_email": r.get("admin_email"), "action": r["action"], "target_type": r.get("target_type"), "target_id": r.get("target_id"), "details": r.get("details"), "created_at": str(r["created_at"]) if r.get("created_at") else None} for r in rows],
        "total": int(total),
    }


@router.get("/security/summary")
def security_summary(admin=Depends(_require_jwt), db: Session = Depends(get_db)):
    s24 = datetime.now(timezone.utc) - timedelta(hours=24)

    audit_24h = 0
    try:
        audit_24h = db.execute(sa_text("SELECT COUNT(*) FROM admin_audit_log WHERE created_at >= :s"), {"s": s24}).scalar() or 0
    except Exception:
        pass

    failed_logins = db.query(func.count(Event.id)).filter(Event.action.in_(["login_failed", "auth_error"]), Event.created_at >= s24).scalar() or 0
    suspicious = db.query(func.count(Event.id)).filter(Event.action.in_(["rate_limited", "forbidden", "suspicious"]), Event.created_at >= s24).scalar() or 0

    return {
        "admin_actions_24h": int(audit_24h),
        "failed_logins_24h": int(failed_logins),
        "suspicious_24h": int(suspicious),
    }


# ═══════════════════════════════════════════════
# CONTROL TOWER — EVENTS & MEMORIES LIST
# ═══════════════════════════════════════════════

@router.get("/events-list")
def events_list(
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    domain: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    q = db.query(Event)
    if domain: q = q.filter(Event.domain == domain)
    if action: q = q.filter(Event.action == action)
    total = q.count()
    rows = q.order_by(desc(Event.created_at)).offset(offset).limit(min(limit, 200)).all()
    return {
        "items": [{"id": e.id, "user_id": e.user_id, "action": e.action, "domain": e.domain, "meta": e.meta, "created_at": e.created_at.isoformat() if e.created_at else None} for e in rows],
        "total": total,
    }


@router.get("/memories-list")
def memories_list(
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    mem_type: Optional[str] = Query(default=None),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    q = db.query(Memory)
    if mem_type: q = q.filter(Memory.type == mem_type)
    total = q.count()
    rows = q.order_by(desc(Memory.created_at)).offset(offset).limit(min(limit, 200)).all()
    return {
        "items": [{"id": m.id, "user_id": m.user_id, "type": m.type, "context": m.context, "input_text": m.input_text, "output_text": m.output_text, "created_at": m.created_at.isoformat() if m.created_at else None} for m in rows],
        "total": total,
    }


# ═══════════════════════════════════════════════
# CONTROL TOWER — MEMBERSHIP
# ═══════════════════════════════════════════════

@router.get("/membership")
def membership(admin=Depends(_require_jwt), db: Session = Depends(get_db)):
    total = db.execute(sa_text("SELECT COUNT(*) FROM users")).scalar() or 0
    prem = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE is_premium = TRUE")).scalar() or 0
    free = int(total) - int(prem)

    s7d = datetime.now(timezone.utc) - timedelta(days=7)
    s30d = datetime.now(timezone.utc) - timedelta(days=30)
    prem_7d = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE is_premium = TRUE AND created_at >= :s"), {"s": s7d}).scalar() or 0
    prem_30d = db.execute(sa_text("SELECT COUNT(*) FROM users WHERE is_premium = TRUE AND created_at >= :s"), {"s": s30d}).scalar() or 0

    vip_clicks = db.query(func.count(Event.id)).filter(Event.action == "vip_click").scalar() or 0
    vip_unlocks = db.query(func.count(Event.id)).filter(Event.action == "vip_unlock").scalar() or 0
    purchases = db.query(func.count(Event.id)).filter(Event.action == "purchase_success").scalar() or 0
    failed_purchases = db.query(func.count(Event.id)).filter(Event.action == "purchase_failed").scalar() or 0

    conversion = round((int(vip_unlocks) / max(int(vip_clicks), 1)) * 100, 1)

    return {
        "total_users": int(total),
        "premium": int(prem),
        "free": int(free),
        "new_premium_7d": int(prem_7d),
        "new_premium_30d": int(prem_30d),
        "vip_clicks": int(vip_clicks),
        "vip_unlocks": int(vip_unlocks),
        "purchases": int(purchases),
        "failed_purchases": int(failed_purchases),
        "conversion_rate": conversion,
    }


# ═══════════════════════════════════════════════
# CONTROL TOWER — LIVE NOTIFICATIONS FEED
# ═══════════════════════════════════════════════


def _iso_utc(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        dt = v
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return str(v)


def _ts_key(v):
    if v is None:
        return 0.0
    if isinstance(v, datetime):
        dt = v
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0
    return 0.0


EVENT_NOTIFY_MAP = {
    "purchase_success": ("Satın alım", "purchase"),
    "vip_unlock": ("VIP / kilit", "purchase"),
    "purchase_failed": ("Ödeme hatası", "system"),
    "purchase_attempt": ("Ödeme denemesi", "comment"),
    "post_submitted": ("Yankı gönderimi", "moderation"),
    "message_sent": ("Mesaj", "comment"),
    "vip_click": ("VIP tıklama", "comment"),
    "login_failed": ("Giriş", "system"),
    "auth_error": ("Kimlik", "system"),
    "rate_limited": ("Güvenlik", "system"),
    "forbidden": ("Güvenlik", "system"),
}


@router.get("/pending-summary")
def pending_summary(admin=Depends(_require_jwt), db: Session = Depends(get_db)):
    bank_n = yanki_n = 0
    try:
        bank_n = int(db.execute(sa_text("SELECT COUNT(*) FROM bank_transfer_requests WHERE status = 'pending'")).scalar() or 0)
    except Exception:
        pass
    try:
        yanki_n = int(db.execute(sa_text("SELECT COUNT(*) FROM yanki_posts WHERE status = 'pending_review'")).scalar() or 0)
    except Exception:
        pass
    return {"bank_transfer_pending": bank_n, "yanki_moderation_pending": yanki_n, "total": bank_n + yanki_n}


@router.get("/notifications-feed")
def notifications_feed(
    limit: int = Query(default=60, ge=1, le=120),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    bucket = []

    try:
        bt_rows = db.execute(
            sa_text(
                "SELECT id, name, email, product_name, content_id, amount, transfer_code, created_at "
                "FROM bank_transfer_requests WHERE status = 'pending' ORDER BY id DESC LIMIT 20"
            )
        ).mappings().all()
        for r in bt_rows:
            ts = r.get("created_at")
            bucket.append(
                (
                    _ts_key(ts),
                    {
                        "id": f"bt-{r['id']}",
                        "type": "purchase",
                        "title": "Havale bekliyor",
                        "text": f"{r.get('name') or '?'} · {r.get('product_name') or ''} · {r.get('amount')} ₺ · {r.get('email') or ''} · {r.get('transfer_code') or ''}",
                        "time": _iso_utc(ts),
                        "read": False,
                        "href": "/admin/banka-odemeleri",
                    },
                )
            )
    except Exception:
        pass

    try:
        yp = db.execute(
            sa_text(
                "SELECT id, title, content_raw, created_at FROM yanki_posts "
                "WHERE status = 'pending_review' ORDER BY created_at DESC LIMIT 15"
            )
        ).mappings().all()
        for r in yp:
            ts = r.get("created_at")
            tid = r["id"]
            raw = (r.get("content_raw") or "").replace("\n", " ")[:200]
            tit = (r.get("title") or "").strip()
            line = (f"{tit}: {raw}" if tit else raw).strip() or f"Gönderi #{tid}"
            bucket.append(
                (
                    _ts_key(ts),
                    {
                        "id": f"yp-{tid}",
                        "type": "moderation",
                        "title": "Yankı onay bekliyor",
                        "text": f"#{tid} · {line[:280]}",
                        "time": _iso_utc(ts),
                        "read": False,
                        "href": "/admin/yanki",
                    },
                )
            )
    except Exception:
        pass

    since_u = datetime.now(timezone.utc) - timedelta(days=7)
    try:
        nu = db.execute(
            sa_text("SELECT id, email, created_at FROM users WHERE created_at >= :s ORDER BY created_at DESC LIMIT 12"),
            {"s": since_u},
        ).mappings().all()
        for r in nu:
            ts = r.get("created_at")
            bucket.append(
                (
                    _ts_key(ts),
                    {
                        "id": f"usr-{r['id']}",
                        "type": "comment",
                        "title": "Yeni üye",
                        "text": r.get("email") or f"user #{r['id']}",
                        "time": _iso_utc(ts),
                        "read": False,
                        "href": "/admin/users",
                    },
                )
            )
    except Exception:
        pass

    try:
        ev_actions = tuple(EVENT_NOTIFY_MAP.keys())
        evs = (
            db.query(Event)
            .filter(Event.action.in_(ev_actions))
            .order_by(desc(Event.created_at))
            .limit(40)
            .all()
        )
        for e in evs:
            title_base, ntype = EVENT_NOTIFY_MAP.get(e.action, ("Olay", "comment"))
            meta = e.meta
            extra = ""
            if isinstance(meta, dict):
                extra = str(meta.get("path") or meta.get("content_id") or meta.get("domain") or "")[:100]
            elif meta:
                extra = str(meta)[:100]
            ts = e.created_at
            dom = f" · {e.domain}" if getattr(e, "domain", None) else ""
            bucket.append(
                (
                    _ts_key(ts),
                    {
                        "id": f"ev-{e.id}",
                        "type": ntype,
                        "title": title_base,
                        "text": f"{e.action}{(' · ' + extra) if extra else ''}{dom}",
                        "time": _iso_utc(ts),
                        "read": False,
                        "href": "/admin/system",
                    },
                )
            )
    except Exception:
        pass

    s24 = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        fro = db.execute(
            sa_text(
                "SELECT id, event_type, source, created_at FROM funnel_events WHERE created_at >= :s ORDER BY created_at DESC LIMIT 25"
            ),
            {"s": s24},
        ).mappings().all()
        for r in fro:
            ts = r.get("created_at")
            et = r.get("event_type") or ""
            src = r.get("source") or ""
            bucket.append(
                (
                    _ts_key(ts),
                    {
                        "id": f"fe-{r['id']}",
                        "type": "comment",
                        "title": "Funnel",
                        "text": f"{et}{(' · ' + src) if src else ''}",
                        "time": _iso_utc(ts),
                        "read": False,
                        "href": "/admin/funnel",
                    },
                )
            )
    except Exception:
        pass

    try:
        aud = db.execute(
            sa_text(
                "SELECT id, admin_email, action, target_type, target_id, created_at FROM admin_audit_log "
                "ORDER BY created_at DESC LIMIT 12"
            )
        ).mappings().all()
        for r in aud:
            ts = r.get("created_at")
            tgt = ""
            if r.get("target_type"):
                tgt = f" · {r.get('target_type')} {r.get('target_id') or ''}"
            bucket.append(
                (
                    _ts_key(ts),
                    {
                        "id": f"au-{r['id']}",
                        "type": "system",
                        "title": "Admin işlemi",
                        "text": f"{r.get('admin_email') or 'admin'}: {r.get('action') or ''}{tgt}",
                        "time": _iso_utc(ts),
                        "read": False,
                        "href": "/admin/system",
                    },
                )
            )
    except Exception:
        pass

    bucket.sort(key=lambda x: x[0], reverse=True)
    out = [x[1] for x in bucket[:limit]]
    seen = set()
    deduped = []
    for it in out:
        iid = it.get("id")
        if iid in seen:
            continue
        seen.add(iid)
        deduped.append(it)
    return {"items": deduped}
