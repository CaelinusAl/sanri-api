from typing import Optional, List
from datetime import datetime
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text, func, inspect

from app.db import get_db, engine, Base
from app.routes.auth import get_current_user
from app.models.yanki import YankiPost, YankiComment, YankiReaction, YankiReport
from app.models.sanri_reflection import SanriReflection
from app.models.notification import YankiNotification

router = APIRouter(prefix="/yanki", tags=["yanki"])

# MVP: auto-publish posts so they appear immediately without admin approval.
# Set YANKI_AUTO_PUBLISH=false in production to require moderation.
AUTO_PUBLISH = os.getenv("YANKI_AUTO_PUBLISH", "true").lower() in ("true", "1", "yes")


# ── Schema migration for existing tables ──────────────────────────
def _migrate_yanki_schema():
    """Add new columns to existing tables created by the old raw-SQL DDL.
    Uses dialect-aware conditional ALTER statements."""

    is_sqlite = str(engine.url).startswith("sqlite")
    insp = inspect(engine)

    def _existing_columns(table_name: str) -> set:
        try:
            return {c["name"] for c in insp.get_columns(table_name)}
        except Exception:
            return set()

    with engine.connect() as conn:
        # -- yanki_posts new columns --
        if insp.has_table("yanki_posts"):
            cols = _existing_columns("yanki_posts")
            adds = {
                "image_url": "VARCHAR",
                "audio_url": "VARCHAR",
                "reaction_sessizce": "INTEGER DEFAULT 0",
                "comment_count": "INTEGER DEFAULT 0",
                "updated_at": "TIMESTAMP",
            }
            for col_name, col_def in adds.items():
                if col_name not in cols:
                    conn.execute(text(
                        f"ALTER TABLE yanki_posts ADD COLUMN {col_name} {col_def}"
                    ))

        # -- yanki_reports: rename user_id -> keep but ensure FK-compatible --
        if insp.has_table("yanki_reports"):
            cols = _existing_columns("yanki_reports")
            if "reporter_user_id" not in cols and "user_id" in cols:
                pass  # keep old column name; ORM maps it

        # -- users: add any missing columns the ORM model expects --
        if insp.has_table("users"):
            cols = _existing_columns("users")
            user_adds = {
                "is_verified": "BOOLEAN DEFAULT FALSE",
                "phone": "VARCHAR",
                "plan": "VARCHAR DEFAULT 'free'",
                "premium_until": "TIMESTAMP",
                "premium_source": "VARCHAR",
                "apple_product_id": "VARCHAR",
                "apple_original_transaction_id": "VARCHAR",
                "matrix_role_unlocked": "BOOLEAN DEFAULT FALSE",
                "last_matrix_deep_analysis": "TIMESTAMP",
                "last_login_at": "TIMESTAMP",
                "last_seen_at": "TIMESTAMP",
                "deletion_requested_at": "TIMESTAMP",
                "account_deleted_at": "TIMESTAMP",
                "display_name": "VARCHAR",
                "avatar_url": "VARCHAR",
                "bio": "TEXT",
                "last_active_date": "VARCHAR",
                "current_streak": "INTEGER DEFAULT 0",
                "longest_streak": "INTEGER DEFAULT 0",
            }
            for col_name, col_def in user_adds.items():
                if col_name not in cols:
                    conn.execute(text(
                        f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"
                    ))

        conn.commit()

    # Create any new tables (yanki_comments, sanri_reflections) that don't exist yet
    Base.metadata.create_all(bind=engine)

try:
    _migrate_yanki_schema()
except Exception as e:
    print(f"[YANKI] Schema migration warning: {e}")


# ── Pydantic Schemas ──────────────────────────────────────────────

# --- Request schemas ---

class CreatePostIn(BaseModel):
    title: Optional[str] = None
    content: str
    category: str = "genel"
    anonymous: bool = True
    image_url: Optional[str] = None
    audio_url: Optional[str] = None

class AdminReviewIn(BaseModel):
    action: str  # "approve" | "reject"
    reject_reason: Optional[str] = None
    sanri_note: Optional[str] = None

class ReactIn(BaseModel):
    reaction_type: str  # "kalbime_dokundu" | "ben_de_hissettim" | "sessizce_aldim"

class ReportIn(BaseModel):
    reason: Optional[str] = None

class CommentIn(BaseModel):
    content: str

class SanriReflectIn(BaseModel):
    prompt: Optional[str] = None

# --- Response schemas ---

class PostOut(BaseModel):
    id: int
    author_mode: str
    author_name: Optional[str] = None
    title: Optional[str] = None
    content: str
    category: str
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    sanri_note: Optional[str] = None
    reaction_heart: int = 0
    reaction_felt: int = 0
    reaction_sessizce: int = 0
    comment_count: int = 0
    created_at: Optional[str] = None
    published_at: Optional[str] = None

class PostListOut(BaseModel):
    posts: List[PostOut]
    total: int
    limit: int
    offset: int

class CommentOut(BaseModel):
    id: int
    post_id: int
    user_id: int
    author_name: Optional[str] = None
    content: str
    created_at: Optional[str] = None

class CommentListOut(BaseModel):
    comments: List[CommentOut]
    total: int

class ReflectionOut(BaseModel):
    id: int
    post_id: int
    user_id: Optional[int] = None
    prompt: str
    response: str
    source: str
    created_at: Optional[str] = None

class ReflectionListOut(BaseModel):
    reflections: List[ReflectionOut]

class CreatePostOut(BaseModel):
    ok: bool
    post_id: int
    status: str
    message: str

class OkOut(BaseModel):
    ok: bool
    action: Optional[str] = None
    message: Optional[str] = None


# ── Constants ─────────────────────────────────────────────────────

VALID_CATEGORIES = [
    "genel", "duygu", "ruya", "soru", "farkindalik",
    "donusum", "isaret", "gunluk_akis", "sesli_yanki", "gorsel_yanki",
]
VALID_REACTIONS = ["kalbime_dokundu", "ben_de_hissettim", "sessizce_aldim"]

REACTION_COL_MAP = {
    "kalbime_dokundu": "reaction_heart",
    "ben_de_hissettim": "reaction_felt",
    "sessizce_aldim": "reaction_sessizce",
}


# ── Notification helper ────────────────────────────────────────────

def _emit_notification(db: Session, user_id: int, notif_type: str, post_id: int, actor_id: int = None, message: str = None):
    """Create a notification for user_id. Skips if actor_id == user_id (no self-notifs)."""
    if actor_id and actor_id == user_id:
        return
    notif = YankiNotification(
        user_id=user_id,
        type=notif_type,
        post_id=post_id,
        actor_id=actor_id,
        message=(message or "")[:500] or None,
    )
    db.add(notif)


# ── Streak helper ─────────────────────────────────────────────────

def _update_streak(db: Session, user_id: int):
    """Increment the user's daily streak if they haven't already been active today."""
    from app.models.user import User
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return

    last = getattr(user, "last_active_date", None)
    if last == today_str:
        return

    yesterday_str = (datetime.utcnow().date() - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")

    current = getattr(user, "current_streak", 0) or 0
    longest = getattr(user, "longest_streak", 0) or 0

    if last == yesterday_str:
        current += 1
    else:
        current = 1

    if current > longest:
        longest = current

    user.last_active_date = today_str
    user.current_streak = current
    user.longest_streak = longest


def _sanitize(text_raw: str) -> str:
    cleaned = text_raw.strip()
    if len(cleaned) > 5000:
        cleaned = cleaned[:5000]
    return cleaned


# ── PUBLIC: List published posts ──────────────────────────────────

@router.get("/posts", response_model=PostListOut)
def list_published(
    category: Optional[str] = Query(None),
    section: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(YankiPost).filter(YankiPost.status == "published")

    if category and category in VALID_CATEGORIES:
        q = q.filter(YankiPost.category == category)

    if section == "today":
        q = q.filter(func.date(YankiPost.published_at) == func.current_date())
    elif section == "curated":
        q = q.filter(YankiPost.sanri_note.isnot(None), YankiPost.sanri_note != "")

    total = q.count()
    posts = q.order_by(YankiPost.published_at.desc()).offset(offset).limit(limit).all()

    return {
        "posts": [p.to_public_dict() for p in posts],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ── PUBLIC: Get single post ──────────────────────────────────────

@router.get("/posts/{post_id}", response_model=PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = (
        db.query(YankiPost)
        .filter(YankiPost.id == post_id, YankiPost.status == "published")
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post bulunamadı.")
    return post.to_public_dict()


# ── AUTH: Create post ─────────────────────────────────────────────

@router.post("/posts", response_model=CreatePostOut)
def create_post(
    payload: CreatePostIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = payload.content.strip()
    if len(content) < 10:
        raise HTTPException(status_code=400, detail="İçerik en az 10 karakter olmalı.")

    category = payload.category if payload.category in VALID_CATEGORIES else "genel"

    now = datetime.utcnow()
    initial_status = "published" if AUTO_PUBLISH else "pending_review"

    post = YankiPost(
        user_id=current_user["id"],
        author_mode="anonymous" if payload.anonymous else "named",
        title=(payload.title or "").strip()[:300] or None,
        content_raw=content,
        content_sanitized=_sanitize(content),
        category=category,
        image_url=payload.image_url,
        audio_url=payload.audio_url,
        status=initial_status,
        published_at=now if AUTO_PUBLISH else None,
    )
    db.add(post)
    _update_streak(db, current_user["id"])
    db.commit()
    db.refresh(post)

    msg = "Yankın yayınlandı!" if AUTO_PUBLISH else "Yankın alındı. İncelendikten sonra yayınlanacak."
    return {
        "ok": True,
        "post_id": post.id,
        "status": post.status,
        "message": msg,
    }


# ── AUTH: My profile with stats ───────────────────────────────────

@router.get("/me/profile")
def my_profile(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = current_user["id"]

    from app.models.user import User
    user = db.query(User).filter(User.id == uid).first()

    post_count = db.query(YankiPost).filter(YankiPost.user_id == uid).count()
    published_count = db.query(YankiPost).filter(
        YankiPost.user_id == uid, YankiPost.status == "published"
    ).count()
    comment_count = db.query(YankiComment).filter(YankiComment.user_id == uid).count()

    total_hearts = db.query(func.coalesce(func.sum(YankiPost.reaction_heart), 0)).filter(
        YankiPost.user_id == uid
    ).scalar()
    total_felt = db.query(func.coalesce(func.sum(YankiPost.reaction_felt), 0)).filter(
        YankiPost.user_id == uid
    ).scalar()
    total_sessizce = db.query(func.coalesce(func.sum(YankiPost.reaction_sessizce), 0)).filter(
        YankiPost.user_id == uid
    ).scalar()

    display_name = None
    bio = None
    avatar_url = None
    email = current_user.get("email")

    if user:
        display_name = getattr(user, "display_name", None)
        bio = getattr(user, "bio", None)
        avatar_url = getattr(user, "avatar_url", None)

    current_streak = 0
    longest_streak = 0
    last_active_date = None
    if user:
        current_streak = getattr(user, "current_streak", 0) or 0
        longest_streak = getattr(user, "longest_streak", 0) or 0
        last_active_date = getattr(user, "last_active_date", None)

    unread_notifs = (
        db.query(YankiNotification)
        .filter(YankiNotification.user_id == uid, YankiNotification.is_read == False)
        .count()
    )

    return {
        "user_id": uid,
        "email": email,
        "display_name": display_name,
        "avatar_url": avatar_url,
        "bio": bio,
        "stats": {
            "post_count": post_count,
            "published_count": published_count,
            "comment_count": comment_count,
            "total_reactions_received": int(total_hearts) + int(total_felt) + int(total_sessizce),
            "reaction_heart": int(total_hearts),
            "reaction_felt": int(total_felt),
            "reaction_sessizce": int(total_sessizce),
        },
        "streak": {
            "current": current_streak,
            "longest": longest_streak,
            "last_active_date": last_active_date,
        },
        "unread_notifications": unread_notifs,
    }


# ── AUTH: Update my profile ──────────────────────────────────────

class UpdateProfileIn(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None

@router.put("/me/profile")
def update_profile(
    payload: UpdateProfileIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.user import User
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()[:100] or None
    if payload.bio is not None:
        user.bio = payload.bio.strip()[:500] or None

    db.commit()
    return {"ok": True, "message": "Profil güncellendi."}


# ── AUTH: My posts (user sees their own including pending) ─────────

@router.get("/me/posts", response_model=PostListOut)
def my_posts(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = current_user["id"]
    q = db.query(YankiPost).filter(YankiPost.user_id == uid)
    total = q.count()
    posts = q.order_by(YankiPost.created_at.desc()).offset(offset).limit(limit).all()

    results = []
    for p in posts:
        d = p.to_public_dict()
        d["status"] = p.status
        results.append(d)

    return {"posts": results, "total": total, "limit": limit, "offset": offset}


# ── AUTH: React to post ───────────────────────────────────────────

@router.post("/posts/{post_id}/react", response_model=OkOut)
def react_to_post(
    post_id: int,
    payload: ReactIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.reaction_type not in VALID_REACTIONS:
        raise HTTPException(status_code=400, detail="Geçersiz reaksiyon.")

    post = (
        db.query(YankiPost)
        .filter(YankiPost.id == post_id, YankiPost.status == "published")
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post bulunamadı.")

    uid = current_user["id"]
    existing = (
        db.query(YankiReaction)
        .filter_by(post_id=post_id, user_id=uid, reaction_type=payload.reaction_type)
        .first()
    )

    counter_attr = REACTION_COL_MAP[payload.reaction_type]

    if existing:
        db.delete(existing)
        setattr(post, counter_attr, max(getattr(post, counter_attr) - 1, 0))
        db.commit()
        return {"ok": True, "action": "removed"}
    else:
        reaction = YankiReaction(
            post_id=post_id,
            user_id=uid,
            reaction_type=payload.reaction_type,
        )
        db.add(reaction)
        setattr(post, counter_attr, getattr(post, counter_attr) + 1)
        if post.user_id:
            _emit_notification(db, post.user_id, "reaction", post_id, actor_id=uid,
                               message=f"Yankına {payload.reaction_type} tepkisi geldi")
        db.commit()
        return {"ok": True, "action": "added"}


# ── AUTH: Report post ─────────────────────────────────────────────

@router.post("/posts/{post_id}/report", response_model=OkOut)
def report_post(
    post_id: int,
    payload: ReportIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    post = db.query(YankiPost).filter(YankiPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post bulunamadı.")

    report = YankiReport(
        post_id=post_id,
        user_id=current_user["id"],
        reason=payload.reason,
    )
    db.add(report)
    post.report_count = post.report_count + 1
    db.commit()
    return {"ok": True, "message": "Bildirim alındı."}


# ── PUBLIC: List comments for a post ──────────────────────────────

@router.get("/posts/{post_id}/comments", response_model=CommentListOut)
def list_comments(
    post_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    post = (
        db.query(YankiPost)
        .filter(YankiPost.id == post_id, YankiPost.status == "published")
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post bulunamadı.")

    total = db.query(YankiComment).filter(YankiComment.post_id == post_id).count()
    comments = (
        db.query(YankiComment)
        .filter(YankiComment.post_id == post_id)
        .order_by(YankiComment.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "comments": [c.to_dict() for c in comments],
        "total": total,
    }


# ── AUTH: Add comment ─────────────────────────────────────────────

@router.post("/posts/{post_id}/comments")
def add_comment(
    post_id: int,
    payload: CommentIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = payload.content.strip()
    if len(content) < 2:
        raise HTTPException(status_code=400, detail="Yorum en az 2 karakter olmalı.")

    post = (
        db.query(YankiPost)
        .filter(YankiPost.id == post_id, YankiPost.status == "published")
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post bulunamadı.")

    comment = YankiComment(
        post_id=post_id,
        user_id=current_user["id"],
        content=content[:2000],
    )
    db.add(comment)
    post.comment_count = post.comment_count + 1
    if post.user_id:
        _emit_notification(db, post.user_id, "comment", post_id, actor_id=current_user["id"],
                           message="Yankına yeni bir yorum geldi")
    db.commit()
    db.refresh(comment)

    return {"ok": True, "comment": comment.to_dict()}


# ── AUTH: Get AI reflection for a post ────────────────────────────

SANRI_SYSTEM_CONTEXT = (
    "Sen Sanrı'sın — bir bilinç aynası. "
    "Kullanıcı Yankı Alanı'nda bir paylaşım yaptı. Bu paylaşıma derin bir yansıma yaz. "
    "Yanıtın ŞU FORMATTA olsun:\n\n"
    "YANSIMA: [1-2 cümlelik kısa analiz — paylaşımın özünü yansıt]\n\n"
    "DERİNLİK: [1 cümle — altta yatan duygu veya ihtiyacı ifade et]\n\n"
    "SORU: [1 düşündürücü soru — kullanıcıyı içe dönmeye davet et]\n\n"
    "Ton: şiirsel, derin ama anlaşılır. Kısa tut, 4-5 cümle yeterli. Türkçe yaz."
)

@router.post("/posts/{post_id}/sanri-reflect", response_model=ReflectionOut)
def sanri_reflect(
    post_id: int,
    payload: SanriReflectIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    post = (
        db.query(YankiPost)
        .filter(YankiPost.id == post_id, YankiPost.status == "published")
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post bulunamadı.")

    existing = (
        db.query(SanriReflection)
        .filter(SanriReflection.post_id == post_id)
        .order_by(SanriReflection.created_at.desc())
        .first()
    )
    if existing:
        return existing.to_dict()

    prompt_text = payload.prompt or post.content_sanitized or post.content_raw

    source = "api"
    try:
        from app.services.sanri_orchestrator import run_sanri
        result = run_sanri(
            db=db,
            user_id=current_user["id"],
            user_message=prompt_text,
            session_id="yanki-reflect",
            lang="tr",
            system_context=SANRI_SYSTEM_CONTEXT,
        )
        response_text = result.get("answer") or result.get("response") or str(result)
    except Exception as e:
        print(f"[YANKI] Sanri reflection API error: {e}")
        source = "fallback"
        response_text = _generate_fallback_reflection(prompt_text)

    reflection = SanriReflection(
        post_id=post_id,
        user_id=current_user["id"],
        prompt=prompt_text[:2000],
        response=response_text[:5000],
        source=source,
    )
    db.add(reflection)
    if post.user_id:
        _emit_notification(db, post.user_id, "sanri", post_id,
                           message="Sanrı yankına bir yansıma bıraktı")
    db.commit()
    db.refresh(reflection)

    return reflection.to_dict()


# ── PUBLIC: List reflections for a post ───────────────────────────

@router.get("/posts/{post_id}/reflections", response_model=ReflectionListOut)
def list_reflections(
    post_id: int,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    reflections = (
        db.query(SanriReflection)
        .filter(SanriReflection.post_id == post_id)
        .order_by(SanriReflection.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"reflections": [r.to_dict() for r in reflections]}


# ── AUTH: My notifications ─────────────────────────────────────────

@router.get("/me/notifications")
def my_notifications(
    limit: int = Query(30, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = current_user["id"]
    notifs = (
        db.query(YankiNotification)
        .filter(YankiNotification.user_id == uid)
        .order_by(YankiNotification.created_at.desc())
        .limit(limit)
        .all()
    )
    unread = (
        db.query(YankiNotification)
        .filter(YankiNotification.user_id == uid, YankiNotification.is_read == False)
        .count()
    )
    return {
        "notifications": [n.to_dict() for n in notifs],
        "unread_count": unread,
    }


@router.post("/me/notifications/read-all")
def mark_all_read(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = current_user["id"]
    db.query(YankiNotification).filter(
        YankiNotification.user_id == uid,
        YankiNotification.is_read == False,
    ).update({"is_read": True})
    db.commit()
    return {"ok": True}


@router.post("/me/notifications/{notif_id}/read")
def mark_one_read(
    notif_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notif = (
        db.query(YankiNotification)
        .filter(YankiNotification.id == notif_id, YankiNotification.user_id == current_user["id"])
        .first()
    )
    if notif:
        notif.is_read = True
        db.commit()
    return {"ok": True}


# ── ADMIN: List pending posts ─────────────────────────────────────

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

    q = db.query(YankiPost).filter(YankiPost.status == status_filter)
    total = q.count()
    posts = q.order_by(YankiPost.created_at.desc()).offset(offset).limit(limit).all()

    return {"posts": [p.to_admin_dict() for p in posts], "total": total}


# ── ADMIN: Review post ───────────────────────────────────────────

@router.post("/admin/posts/{post_id}/review")
def admin_review_post(
    post_id: int,
    payload: AdminReviewIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    post = db.query(YankiPost).filter(YankiPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post bulunamadı.")

    now = datetime.utcnow()

    if payload.action == "approve":
        post.status = "published"
        post.sanri_note = payload.sanri_note
        post.reviewed_at = now
        post.published_at = now
    elif payload.action == "reject":
        post.status = "rejected"
        post.reject_reason = payload.reject_reason
        post.reviewed_at = now
    else:
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    db.commit()
    return {"ok": True, "post_id": post_id, "action": payload.action}


# ── ADMIN: Stats ──────────────────────────────────────────────────

@router.get("/admin/stats")
def admin_stats(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    stats = {}
    for st in ["pending_review", "published", "rejected"]:
        stats[st] = db.query(YankiPost).filter(YankiPost.status == st).count()

    stats["total_reactions"] = db.query(YankiReaction).count()
    stats["total_reports"] = db.query(YankiReport).count()
    stats["total_comments"] = db.query(YankiComment).count()
    stats["total_reflections"] = db.query(SanriReflection).count()

    return stats


# ── Fallback reflection generator ─────────────────────────────────

_FALLBACK_POOL = [
    {
        "yansima": "Bu paylaşımın ardında derin bir farkındalık yatıyor. Kelimeler bazen içsel depremlerin yüzeye çıkış biçimidir.",
        "derinlik": "Bastırılan her duygu bir gün başka bir biçimde konuşur — burada konuşması cesaret işareti.",
        "soru": "Bu duygunun altında senden ne istediğini hiç sordun mu?",
    },
    {
        "yansima": "Bazen en güçlü dönüşümler sessiz kelimelerle başlar. Senin kelimelerin de böyle — sessiz ama derin.",
        "derinlik": "Sessizlik boşluk değildir; dinlemenin en saf halidir.",
        "soru": "Sessizliğin sana ne söylediğini son ne zaman dinledin?",
    },
    {
        "yansima": "İçsel yolculuğunun bu anı bir kapının eşiğidir. Eşikte durmak bile cesaret ister.",
        "derinlik": "Geçiş anları rahatsız eder çünkü eski ile yeni arasında boşluk vardır — o boşluk büyüme alanıdır.",
        "soru": "Bugün hangi kapının eşiğindesin?",
    },
    {
        "yansima": "Paylaştığın her söz kolektif bilinçte bir dalga yaratır. Bu dalga senden büyük.",
        "derinlik": "Bireysel acı kolektif şifanın tohumudur — paylaşmak hem seni hem başkalarını iyileştirir.",
        "soru": "Bu yankının kime ulaşmasını isterdin?",
    },
    {
        "yansima": "Bu düşüncenin altında keşfedilmeyi bekleyen katmanlar var. Her katman bir derse açılıyor.",
        "derinlik": "Yüzeydeki his nadiren gerçek histir — altına indiğinde asıl mesajı bulursun.",
        "soru": "Bu hissin bir altına insen ne bulursun?",
    },
]

def _generate_fallback_reflection(content: str) -> str:
    idx = len(content) % len(_FALLBACK_POOL)
    r = _FALLBACK_POOL[idx]
    return f"YANSIMA: {r['yansima']}\n\nDERİNLİK: {r['derinlik']}\n\nSORU: {r['soru']}"
