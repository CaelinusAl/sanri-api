from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db, engine
from app.routes.auth import get_current_user

router = APIRouter(prefix="/yanki", tags=["yanki"])


# ── Auto-create tables ──
def _ensure_tables():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS yanki_posts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                author_mode VARCHAR(20) DEFAULT 'anonymous',
                title VARCHAR(300),
                content_raw TEXT NOT NULL,
                content_sanitized TEXT,
                category VARCHAR(50) DEFAULT 'genel',
                status VARCHAR(20) DEFAULT 'pending_review',
                sanri_note TEXT,
                reject_reason TEXT,
                reaction_heart INTEGER DEFAULT 0,
                reaction_felt INTEGER DEFAULT 0,
                report_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                reviewed_at TIMESTAMP,
                published_at TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS yanki_reactions (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL,
                user_id INTEGER,
                reaction_type VARCHAR(30) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(post_id, user_id, reaction_type)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS yanki_reports (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL,
                user_id INTEGER,
                reason TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()

try:
    _ensure_tables()
except Exception as e:
    print(f"[YANKI] Table migration warning: {e}")


# ── Schemas ──
class CreatePostIn(BaseModel):
    title: Optional[str] = None
    content: str
    category: str = "genel"
    anonymous: bool = True

class AdminReviewIn(BaseModel):
    action: str  # "approve" or "reject"
    reject_reason: Optional[str] = None
    sanri_note: Optional[str] = None

class ReactIn(BaseModel):
    reaction_type: str  # "kalbime_dokundu" or "ben_de_hissettim"

class ReportIn(BaseModel):
    reason: Optional[str] = None


# ── Helpers ──
VALID_CATEGORIES = ["genel", "duygu", "ruya", "soru", "farkindalik", "donusum"]
VALID_REACTIONS = ["kalbime_dokundu", "ben_de_hissettim"]

def _sanitize(text_raw: str) -> str:
    """Basic sanitization - strip extreme whitespace, limit length."""
    cleaned = text_raw.strip()
    if len(cleaned) > 5000:
        cleaned = cleaned[:5000]
    return cleaned


# ── PUBLIC: List published posts ──
@router.get("/posts")
def list_published(
    category: Optional[str] = Query(None),
    section: Optional[str] = Query(None),  # "today" | "new" | "curated"
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    where = "WHERE status = 'published'"
    params = {"limit": limit, "offset": offset}

    if category and category in VALID_CATEGORIES:
        where += " AND category = :cat"
        params["cat"] = category

    order = "ORDER BY published_at DESC"
    if section == "today":
        where += " AND published_at >= CURRENT_DATE"
    elif section == "curated":
        where += " AND sanri_note IS NOT NULL AND sanri_note != ''"

    rows = db.execute(
        text(f"""
            SELECT id, author_mode, title, content_sanitized, category,
                   sanri_note, reaction_heart, reaction_felt,
                   created_at, published_at
            FROM yanki_posts
            {where}
            {order}
            LIMIT :limit OFFSET :offset
        """),
        params,
    ).mappings().all()

    total = db.execute(
        text(f"SELECT COUNT(*) FROM yanki_posts {where}"),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    ).scalar()

    return {
        "posts": [dict(r) for r in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


# ── PUBLIC: Get single post ──
@router.get("/posts/{post_id}")
def get_post(post_id: int, db: Session = Depends(get_db)):
    row = db.execute(
        text("""
            SELECT id, author_mode, title, content_sanitized, category,
                   sanri_note, reaction_heart, reaction_felt,
                   created_at, published_at
            FROM yanki_posts
            WHERE id = :pid AND status = 'published'
        """),
        {"pid": post_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Post bulunamadı.")
    return dict(row)


# ── AUTH: Create post ──
@router.post("/posts")
def create_post(
    payload: CreatePostIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = payload.content.strip()
    if len(content) < 10:
        raise HTTPException(status_code=400, detail="İçerik en az 10 karakter olmalı.")

    category = payload.category if payload.category in VALID_CATEGORIES else "genel"

    row = db.execute(
        text("""
            INSERT INTO yanki_posts (user_id, author_mode, title, content_raw, content_sanitized, category, status)
            VALUES (:uid, :mode, :title, :raw, :sanitized, :cat, 'pending_review')
            RETURNING id, status, created_at
        """),
        {
            "uid": current_user["id"],
            "mode": "anonymous" if payload.anonymous else "named",
            "title": (payload.title or "").strip()[:300] or None,
            "raw": content,
            "sanitized": _sanitize(content),
            "cat": category,
        },
    ).mappings().first()
    db.commit()

    return {
        "ok": True,
        "post_id": row["id"],
        "status": row["status"],
        "message": "Yankın alındı. İncelendikten sonra yayınlanacak.",
    }


# ── AUTH: React to post ──
@router.post("/posts/{post_id}/react")
def react_to_post(
    post_id: int,
    payload: ReactIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.reaction_type not in VALID_REACTIONS:
        raise HTTPException(status_code=400, detail="Geçersiz reaksiyon.")

    post = db.execute(
        text("SELECT id FROM yanki_posts WHERE id = :pid AND status = 'published'"),
        {"pid": post_id},
    ).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post bulunamadı.")

    existing = db.execute(
        text("SELECT id FROM yanki_reactions WHERE post_id = :pid AND user_id = :uid AND reaction_type = :rt"),
        {"pid": post_id, "uid": current_user["id"], "rt": payload.reaction_type},
    ).first()

    col = "reaction_heart" if payload.reaction_type == "kalbime_dokundu" else "reaction_felt"

    if existing:
        db.execute(text("DELETE FROM yanki_reactions WHERE post_id = :pid AND user_id = :uid AND reaction_type = :rt"),
                   {"pid": post_id, "uid": current_user["id"], "rt": payload.reaction_type})
        db.execute(text(f"UPDATE yanki_posts SET {col} = GREATEST({col} - 1, 0) WHERE id = :pid"), {"pid": post_id})
        db.commit()
        return {"ok": True, "action": "removed"}
    else:
        db.execute(text("INSERT INTO yanki_reactions (post_id, user_id, reaction_type) VALUES (:pid, :uid, :rt)"),
                   {"pid": post_id, "uid": current_user["id"], "rt": payload.reaction_type})
        db.execute(text(f"UPDATE yanki_posts SET {col} = {col} + 1 WHERE id = :pid"), {"pid": post_id})
        db.commit()
        return {"ok": True, "action": "added"}


# ── AUTH: Report post ──
@router.post("/posts/{post_id}/report")
def report_post(
    post_id: int,
    payload: ReportIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.execute(
        text("INSERT INTO yanki_reports (post_id, user_id, reason) VALUES (:pid, :uid, :reason)"),
        {"pid": post_id, "uid": current_user["id"], "reason": payload.reason},
    )
    db.execute(
        text("UPDATE yanki_posts SET report_count = report_count + 1 WHERE id = :pid"),
        {"pid": post_id},
    )
    db.commit()
    return {"ok": True, "message": "Bildirim alındı."}


# ── ADMIN: List pending posts ──
@router.get("/admin/posts")
def admin_list_posts(
    status_filter: str = Query("pending_review"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    rows = db.execute(
        text("""
            SELECT id, user_id, author_mode, title, content_raw, category, status,
                   sanri_note, reject_reason, report_count, created_at, reviewed_at, published_at
            FROM yanki_posts
            WHERE status = :st
            ORDER BY created_at DESC
            LIMIT :lim OFFSET :off
        """),
        {"st": status_filter, "lim": limit, "off": offset},
    ).mappings().all()

    total = db.execute(
        text("SELECT COUNT(*) FROM yanki_posts WHERE status = :st"),
        {"st": status_filter},
    ).scalar()

    return {"posts": [dict(r) for r in rows], "total": total or 0}


# ── ADMIN: Review post ──
@router.post("/admin/posts/{post_id}/review")
def admin_review_post(
    post_id: int,
    payload: AdminReviewIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    if payload.action == "approve":
        db.execute(
            text("""
                UPDATE yanki_posts
                SET status = 'published',
                    sanri_note = :note,
                    reviewed_at = :now,
                    published_at = :now
                WHERE id = :pid
            """),
            {"note": payload.sanri_note, "now": datetime.utcnow(), "pid": post_id},
        )
    elif payload.action == "reject":
        db.execute(
            text("""
                UPDATE yanki_posts
                SET status = 'rejected',
                    reject_reason = :reason,
                    reviewed_at = :now
                WHERE id = :pid
            """),
            {"reason": payload.reject_reason, "now": datetime.utcnow(), "pid": post_id},
        )
    else:
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    db.commit()
    return {"ok": True, "post_id": post_id, "action": payload.action}


# ── ADMIN: Stats ──
@router.get("/admin/stats")
def admin_stats(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    stats = {}
    for st in ["pending_review", "published", "rejected"]:
        count = db.execute(
            text("SELECT COUNT(*) FROM yanki_posts WHERE status = :st"),
            {"st": st},
        ).scalar()
        stats[st] = count or 0

    stats["total_reactions"] = db.execute(
        text("SELECT COUNT(*) FROM yanki_reactions")
    ).scalar() or 0

    stats["total_reports"] = db.execute(
        text("SELECT COUNT(*) FROM yanki_reports")
    ).scalar() or 0

    return stats
