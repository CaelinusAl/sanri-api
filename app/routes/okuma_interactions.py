"""Comments & likes for Okuma Alanı posts — persisted in PostgreSQL."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.db import get_db, engine

router = APIRouter(prefix="/okuma", tags=["okuma"])


def _ensure_tables():
    with engine.connect() as conn:
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS okuma_comments (
                id SERIAL PRIMARY KEY,
                post_slug VARCHAR(200) NOT NULL,
                author_name VARCHAR(100) NOT NULL DEFAULT 'Anonim',
                content TEXT NOT NULL,
                user_id INTEGER,
                ip_hash VARCHAR(64),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS idx_oc_slug ON okuma_comments(post_slug)
        """))
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS okuma_likes (
                id SERIAL PRIMARY KEY,
                post_slug VARCHAR(200) NOT NULL,
                ip_hash VARCHAR(64) NOT NULL,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(post_slug, ip_hash)
            )
        """))
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS idx_ol_slug ON okuma_likes(post_slug)
        """))
        conn.commit()


def _ensure_view_table():
    with engine.connect() as conn:
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS okuma_views (
                id SERIAL PRIMARY KEY,
                post_slug VARCHAR(200) NOT NULL,
                ip_hash VARCHAR(64) NOT NULL,
                session_id VARCHAR(128),
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(post_slug, ip_hash)
            )
        """))
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS idx_ov_slug ON okuma_views(post_slug)
        """))
        conn.commit()


try:
    _ensure_tables()
    _ensure_view_table()
except Exception as e:
    print(f"[OKUMA] Table migration: {e}")


def _ip_hash(request: Request) -> str:
    import hashlib
    client_ip = request.headers.get("x-forwarded-for", request.client.host or "")
    return hashlib.sha256(client_ip.encode()).hexdigest()[:16]


def _get_user_id(request: Request) -> Optional[int]:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            from app.services.auth import decode_token
            payload = decode_token(auth.replace("Bearer ", "").strip())
            if payload:
                uid = payload.get("sub")
                return int(uid) if uid else None
        except Exception:
            pass
    return None


# ── Comments ──

class CommentIn(BaseModel):
    post_slug: str
    author_name: Optional[str] = "Anonim"
    content: str


@router.post("/comments")
def add_comment(body: CommentIn, request: Request, db: Session = Depends(get_db)):
    if not body.content.strip():
        return {"error": "Yorum boş olamaz"}, 400

    ip = _ip_hash(request)
    uid = _get_user_id(request)

    db.execute(sa_text("""
        INSERT INTO okuma_comments (post_slug, author_name, content, user_id, ip_hash, created_at)
        VALUES (:slug, :name, :content, :uid, :ip, NOW())
    """), {
        "slug": body.post_slug[:200],
        "name": (body.author_name or "Anonim")[:100],
        "content": body.content[:2000],
        "uid": uid,
        "ip": ip,
    })
    db.commit()
    return {"ok": True}


@router.get("/comments/{post_slug}")
def get_comments(post_slug: str, db: Session = Depends(get_db)):
    rows = db.execute(sa_text("""
        SELECT id, author_name, content, created_at
        FROM okuma_comments
        WHERE post_slug = :slug
        ORDER BY created_at ASC
    """), {"slug": post_slug}).mappings().all()

    return {
        "comments": [
            {
                "id": r["id"],
                "authorName": r["author_name"],
                "content": r["content"],
                "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    }


# ── Likes ──

@router.post("/like/{post_slug}")
def toggle_like(post_slug: str, request: Request, db: Session = Depends(get_db)):
    ip = _ip_hash(request)

    existing = db.execute(sa_text("""
        SELECT id FROM okuma_likes WHERE post_slug = :slug AND ip_hash = :ip
    """), {"slug": post_slug, "ip": ip}).fetchone()

    if existing:
        db.execute(sa_text("""
            DELETE FROM okuma_likes WHERE post_slug = :slug AND ip_hash = :ip
        """), {"slug": post_slug, "ip": ip})
        db.commit()
        liked = False
    else:
        uid = _get_user_id(request)
        db.execute(sa_text("""
            INSERT INTO okuma_likes (post_slug, ip_hash, user_id, created_at)
            VALUES (:slug, :ip, :uid, NOW())
            ON CONFLICT (post_slug, ip_hash) DO NOTHING
        """), {"slug": post_slug, "ip": ip, "uid": uid})
        db.commit()
        liked = True

    count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_likes WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0

    return {"liked": liked, "count": int(count)}


@router.get("/likes/{post_slug}")
def get_likes(post_slug: str, request: Request, db: Session = Depends(get_db)):
    ip = _ip_hash(request)

    count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_likes WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0

    user_liked = db.execute(sa_text("""
        SELECT id FROM okuma_likes WHERE post_slug = :slug AND ip_hash = :ip
    """), {"slug": post_slug, "ip": ip}).fetchone()

    return {"count": int(count), "liked": bool(user_liked)}


@router.post("/view/{post_slug}")
def record_view(post_slug: str, request: Request, db: Session = Depends(get_db)):
    """Record a unique view per IP for a post."""
    ip = _ip_hash(request)
    uid = _get_user_id(request)
    sid = request.headers.get("x-session-id", "")

    db.execute(sa_text("""
        INSERT INTO okuma_views (post_slug, ip_hash, session_id, user_id, created_at)
        VALUES (:slug, :ip, :sid, :uid, NOW())
        ON CONFLICT (post_slug, ip_hash) DO NOTHING
    """), {"slug": post_slug[:200], "ip": ip, "sid": sid[:128] if sid else None, "uid": uid})
    db.commit()

    count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_views WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0

    return {"ok": True, "count": int(count)}


@router.get("/views/{post_slug}")
def get_views(post_slug: str, db: Session = Depends(get_db)):
    count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_views WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0
    return {"count": int(count)}


@router.get("/views-batch")
def get_views_batch(slugs: str = "", db: Session = Depends(get_db)):
    """Get view counts for multiple slugs. Pass comma-separated slugs."""
    slug_list = [s.strip() for s in slugs.split(",") if s.strip()]
    if not slug_list:
        return {"views": {}}

    rows = db.execute(sa_text("""
        SELECT post_slug, COUNT(*) as cnt
        FROM okuma_views
        WHERE post_slug = ANY(:slugs)
        GROUP BY post_slug
    """), {"slugs": slug_list}).mappings().all()

    return {"views": {r["post_slug"]: int(r["cnt"]) for r in rows}}


@router.get("/stats/{post_slug}")
def get_post_stats(post_slug: str, request: Request, db: Session = Depends(get_db)):
    """Combined stats: comments count, likes count, views count, user liked status."""
    ip = _ip_hash(request)

    comments_count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_comments WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0

    likes_count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_likes WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0

    views_count = db.execute(sa_text("""
        SELECT COUNT(*) FROM okuma_views WHERE post_slug = :slug
    """), {"slug": post_slug}).scalar() or 0

    user_liked = db.execute(sa_text("""
        SELECT id FROM okuma_likes WHERE post_slug = :slug AND ip_hash = :ip
    """), {"slug": post_slug, "ip": ip}).fetchone()

    return {
        "commentsCount": int(comments_count),
        "likesCount": int(likes_count),
        "viewsCount": int(views_count),
        "liked": bool(user_liked),
    }


@router.get("/all-stats")
def get_all_stats(db: Session = Depends(get_db)):
    """Aggregated stats for all posts — used by admin and listing page."""
    views = db.execute(sa_text("""
        SELECT post_slug, COUNT(*) as cnt FROM okuma_views GROUP BY post_slug
    """)).mappings().all()

    likes = db.execute(sa_text("""
        SELECT post_slug, COUNT(*) as cnt FROM okuma_likes GROUP BY post_slug
    """)).mappings().all()

    comments = db.execute(sa_text("""
        SELECT post_slug, COUNT(*) as cnt FROM okuma_comments GROUP BY post_slug
    """)).mappings().all()

    v = {r["post_slug"]: int(r["cnt"]) for r in views}
    l = {r["post_slug"]: int(r["cnt"]) for r in likes}
    c = {r["post_slug"]: int(r["cnt"]) for r in comments}

    all_slugs = set(v) | set(l) | set(c)
    result = {}
    for s in all_slugs:
        result[s] = {"views": v.get(s, 0), "likes": l.get(s, 0), "comments": c.get(s, 0)}

    return {"stats": result}
