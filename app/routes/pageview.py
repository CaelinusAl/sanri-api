"""Anonymous page view tracking for admin analytics."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, text as sa_text

from app.db import get_db, engine

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _ensure_pageview_table():
    with engine.connect() as conn:
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS page_views (
                id SERIAL PRIMARY KEY,
                path VARCHAR(500) NOT NULL,
                referrer VARCHAR(1000),
                user_agent VARCHAR(1000),
                ip_hash VARCHAR(64),
                session_id VARCHAR(64),
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS idx_pv_created ON page_views(created_at)
        """))
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS idx_pv_path ON page_views(path)
        """))
        conn.commit()


try:
    _ensure_pageview_table()
except Exception as e:
    print(f"[PAGEVIEW] Table migration: {e}")


class PageViewIn(BaseModel):
    path: str
    referrer: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/pageview")
def track_pageview(body: PageViewIn, request: Request, db: Session = Depends(get_db)):
    import hashlib
    client_ip = request.headers.get("x-forwarded-for", request.client.host or "")
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]
    ua = (request.headers.get("user-agent") or "")[:1000]

    user_id = None
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            from app.services.auth import decode_token
            payload = decode_token(auth.replace("Bearer ", "").strip())
            if payload:
                user_id = payload.get("sub")
        except Exception:
            pass

    db.execute(sa_text("""
        INSERT INTO page_views (path, referrer, user_agent, ip_hash, session_id, user_id, created_at)
        VALUES (:path, :ref, :ua, :ip, :sid, :uid, NOW())
    """), {
        "path": body.path[:500],
        "ref": (body.referrer or "")[:1000] or None,
        "ua": ua,
        "ip": ip_hash,
        "sid": (body.session_id or "")[:64] or None,
        "uid": int(user_id) if user_id else None,
    })
    db.commit()
    return {"ok": True}


@router.get("/stats")
def analytics_stats(db: Session = Depends(get_db)):
    """Public-safe aggregate stats (no PII)."""
    now = datetime.now(timezone.utc)
    s24 = now - timedelta(hours=24)
    s7d = now - timedelta(days=7)
    s30d = now - timedelta(days=30)

    total = db.execute(sa_text("SELECT COUNT(*) FROM page_views")).scalar() or 0
    today = db.execute(sa_text("SELECT COUNT(*) FROM page_views WHERE created_at >= :s"), {"s": s24}).scalar() or 0
    week = db.execute(sa_text("SELECT COUNT(*) FROM page_views WHERE created_at >= :s"), {"s": s7d}).scalar() or 0
    month = db.execute(sa_text("SELECT COUNT(*) FROM page_views WHERE created_at >= :s"), {"s": s30d}).scalar() or 0

    unique_today = db.execute(sa_text("SELECT COUNT(DISTINCT ip_hash) FROM page_views WHERE created_at >= :s"), {"s": s24}).scalar() or 0
    unique_week = db.execute(sa_text("SELECT COUNT(DISTINCT ip_hash) FROM page_views WHERE created_at >= :s"), {"s": s7d}).scalar() or 0
    unique_month = db.execute(sa_text("SELECT COUNT(DISTINCT ip_hash) FROM page_views WHERE created_at >= :s"), {"s": s30d}).scalar() or 0

    top_pages = db.execute(sa_text("""
        SELECT path, COUNT(*) as c FROM page_views
        WHERE created_at >= :s GROUP BY path ORDER BY c DESC LIMIT 10
    """), {"s": s7d}).mappings().all()

    return {
        "views": {"total": int(total), "today": int(today), "week": int(week), "month": int(month)},
        "unique_visitors": {"today": int(unique_today), "week": int(unique_week), "month": int(unique_month)},
        "top_pages": [{"path": r["path"], "views": int(r["c"])} for r in top_pages],
    }
