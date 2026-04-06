from typing import Optional, List
from datetime import datetime, timedelta
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text, func, inspect

from app.db import get_db, engine, Base
from app.routes.auth import get_current_user
from app.models.yanki import YankiPost, YankiComment, YankiReaction, YankiReport
from app.models.sanri_reflection import SanriReflection
from app.models.notification import YankiNotification
from app.models.referral import YankiReferral

router = APIRouter(prefix="/yanki", tags=["yanki"])

AUTO_PUBLISH = os.getenv("YANKI_AUTO_PUBLISH", "true").lower() in ("true", "1", "yes")


# ── Schema migration for existing tables ──────────────────────────
def _migrate_yanki_schema():
    """Add new columns to existing tables created by the old raw-SQL DDL."""

    insp = inspect(engine)

    def _existing_columns(table_name: str) -> set:
        try:
            return {c["name"] for c in insp.get_columns(table_name)}
        except Exception:
            return set()

    with engine.connect() as conn:
        if insp.has_table("yanki_posts"):
            cols = _existing_columns("yanki_posts")
            adds = {
                "image_url": "VARCHAR",
                "audio_url": "VARCHAR",
                "reaction_sessizce": "INTEGER DEFAULT 0",
                "comment_count": "INTEGER DEFAULT 0",
                "updated_at": "TIMESTAMP",
                "frequency_hz": "INTEGER",
                "energy_feel": "VARCHAR(120)",
                "post_source": "VARCHAR(30) DEFAULT 'classic'",
                "anlasilma_session_id": "VARCHAR(80)",
                "field_echo_count": "INTEGER DEFAULT 0",
            }
            for col_name, col_def in adds.items():
                if col_name not in cols:
                    conn.execute(text(
                        f"ALTER TABLE yanki_posts ADD COLUMN {col_name} {col_def}"
                    ))

        if insp.has_table("users"):
            cols = _existing_columns("users")
            user_adds = {
                "is_verified": "BOOLEAN DEFAULT FALSE",
                "phone": "VARCHAR",
                "plan": "VARCHAR DEFAULT 'free'",
                "is_premium": "BOOLEAN DEFAULT FALSE",
                "premium_until": "TIMESTAMP",
                "premium_source": "VARCHAR",
                "stripe_customer_id": "VARCHAR",
                "apple_product_id": "VARCHAR",
                "apple_original_transaction_id": "VARCHAR",
                "matrix_role_unlocked": "BOOLEAN DEFAULT FALSE",
                "free_unlock_used": "BOOLEAN DEFAULT FALSE",
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

    Base.metadata.create_all(bind=engine)

try:
    _migrate_yanki_schema()
except Exception as e:
    print(f"[YANKI] Schema migration warning: {e}")


# ── Pydantic Schemas ──────────────────────────────────────────────

class CreatePostIn(BaseModel):
    title: Optional[str] = None
    content: str
    category: str = "genel"
    anonymous: bool = True
    image_url: Optional[str] = None
    audio_url: Optional[str] = None

class AdminReviewIn(BaseModel):
    action: str
    reject_reason: Optional[str] = None
    sanri_note: Optional[str] = None

class ReactIn(BaseModel):
    reaction_type: str

class ReportIn(BaseModel):
    reason: Optional[str] = None

class CommentIn(BaseModel):
    content: str

class SanriReflectIn(BaseModel):
    prompt: Optional[str] = None

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
    "frekans_alani",
]
VALID_REACTIONS = ["kalbime_dokundu", "ben_de_hissettim", "sessizce_aldim"]

REACTION_COL_MAP = {
    "kalbime_dokundu": "reaction_heart",
    "ben_de_hissettim": "reaction_felt",
    "sessizce_aldim": "reaction_sessizce",
}


# ── Notification helper ────────────────────────────────────────────

def _emit_notification(db: Session, user_id: int, notif_type: str, post_id: int, actor_id: int = None, message: str = None):
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
    from app.models.user import User

    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Istanbul")
        today_local = datetime.now(tz).date()
    except Exception:
        today_local = datetime.utcnow().date()

    today_str = today_local.strftime("%Y-%m-%d")
    yesterday_str = (today_local - timedelta(days=1)).strftime("%Y-%m-%d")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return

    last = getattr(user, "last_active_date", None)
    if last == today_str:
        return

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


# ── PUBLIC: OG meta HTML for crawlers ────────────────────────────

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://asksanri.com")

@router.get("/og/{post_id}", response_class=HTMLResponse)
def og_meta_page(post_id: int, db: Session = Depends(get_db)):
    """Serve minimal HTML with OG tags for social media crawlers."""
    post = (
        db.query(YankiPost)
        .filter(YankiPost.id == post_id, YankiPost.status == "published")
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    d = post.to_public_dict()
    title = d.get("title") or "Yankı Alanı"
    content = (d.get("content") or "")[:200]
    category = d.get("category", "genel")
    author = d.get("author_name") or "Anonim"
    canonical = f"{FRONTEND_URL}/yanki/{post_id}"
    og_image = f"{FRONTEND_URL}/assets/og/yanki-share.jpg"
    description = f"{content}... — {author}"

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8"/>
<title>{title} — Yankı Alanı</title>
<meta name="description" content="{description}"/>
<meta property="og:type" content="article"/>
<meta property="og:title" content="{title} — Yankı Alanı"/>
<meta property="og:description" content="{description}"/>
<meta property="og:url" content="{canonical}"/>
<meta property="og:image" content="{og_image}"/>
<meta property="og:site_name" content="CAELINUS AI — SANRI"/>
<meta name="twitter:card" content="summary_large_image"/>
<meta name="twitter:title" content="{title} — Yankı Alanı"/>
<meta name="twitter:description" content="{description}"/>
<meta name="twitter:image" content="{og_image}"/>
<meta http-equiv="refresh" content="0;url={canonical}"/>
<link rel="canonical" href="{canonical}"/>
</head>
<body>
<p>Redirecting to <a href="{canonical}">{title}</a>...</p>
</body>
</html>"""
    return HTMLResponse(content=html)


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


# ── PUBLIC: Featured post (Gunun Yankisi) ────────────────────────

@router.get("/posts/featured")
def featured_post(db: Session = Depends(get_db)):
    """Return today's most-interacted published post."""
    today = datetime.utcnow().date()

    q = db.query(YankiPost).filter(YankiPost.status == "published")

    candidates = q.order_by(
        (YankiPost.reaction_heart + YankiPost.reaction_felt
         + YankiPost.reaction_sessizce + YankiPost.comment_count).desc(),
        YankiPost.published_at.desc(),
    ).limit(10).all()

    if not candidates:
        return {"post": None}

    day_seed = today.toordinal()
    top = candidates[0]
    total_top = (top.reaction_heart + top.reaction_felt
                 + top.reaction_sessizce + top.comment_count)

    if total_top > 0:
        pick = top
    else:
        pick = candidates[day_seed % len(candidates)]

    d = pick.to_public_dict()
    d["is_featured"] = True
    return {"post": d}


# ── PUBLIC: Daily question ───────────────────────────────────────

_DAILY_QUESTIONS = [
    "Bugün seni en çok ne durdurdu?",
    "Şu an bedeninde nereyi hissediyorsun?",
    "Bugün hangi duyguyu bastırdın?",
    "Son bir haftada en çok tekrar eden düşüncen ne?",
    "Korktuğun ama istediğin şey ne?",
    "Bugün kime teşekkür etmedin?",
    "Şu an bırakman gereken şey ne?",
    "Son gördüğün rüyada ne vardı?",
    "Seni en çok ne yoruyor?",
    "Bugün kendine ne söyledin?",
    "Hayatında sessizce değişen ne var?",
    "Hangi alışkanlığın seni tutuyor?",
    "Bugün neyi ertelemeden yaptın?",
    "İçindeki çocuk şu an ne istiyor?",
    "Sana en son ne ilham verdi?",
    "Bugün hangi sesi duymadın?",
    "Gerçekten dinlediğin son kişi kimdi?",
    "Neyin değişmesini bekliyorsun?",
    "Bugün en dürüst anın hangisiydi?",
    "Sessizlikte ne duyuyorsun?",
    "Hangi ilişkin sana ayna tutuyor?",
    "Bugün hangi maskeyi taktın?",
    "Seni en çok kızdıran şeyin altında ne var?",
    "Bugün neyi ilk kez fark ettin?",
    "Hangi anda tamamen kendin oldun?",
    "Beden ne söylüyor, zihin ne söylüyor?",
    "Bugün sana gelen işaret ne?",
    "Neye inanmayı bıraktın?",
    "Seni tutan tek düşünce ne?",
    "Bugün kalbin ne istedi?",
    "Hayatında fazla olan ne, eksik olan ne?",
]


@router.get("/daily-question")
def daily_question():
    """Return today's consciousness question."""
    today = datetime.utcnow().date()
    idx = today.toordinal() % len(_DAILY_QUESTIONS)
    return {"question": _DAILY_QUESTIONS[idx], "day": today.isoformat()}


# ── PUBLIC: Share-landing preview ─────────────────────────────────

@router.get("/posts/{post_id}/preview")
def post_preview(post_id: int, ref: Optional[int] = None, db: Session = Depends(get_db)):
    """Minimal public preview for share-landing pages (no auth)."""
    post = (
        db.query(YankiPost)
        .filter(YankiPost.id == post_id, YankiPost.status == "published")
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post bulunamadi.")

    d = post.to_public_dict()

    referrer_name = None
    if ref:
        row = db.execute(
            text("SELECT display_name, email FROM users WHERE id = :uid LIMIT 1"),
            {"uid": ref},
        ).fetchone()
        if row:
            referrer_name = row[0] or (row[1].split("@")[0] if row[1] else None)

    return {
        "post": {
            "id": d["id"],
            "content": d.get("content", "")[:280],
            "title": d.get("title"),
            "category": d.get("category"),
            "author_name": d.get("author_name"),
            "author_mode": d.get("author_mode"),
            "reaction_heart": d.get("reaction_heart", 0),
            "reaction_felt": d.get("reaction_felt", 0),
            "reaction_sessizce": d.get("reaction_sessizce", 0),
            "comment_count": d.get("comment_count", 0),
            "created_at": d.get("created_at"),
        },
        "referrer_name": referrer_name,
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
        raise HTTPException(status_code=404, detail="Post bulunamadi.")
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
        raise HTTPException(status_code=400, detail="Icerik en az 10 karakter olmali.")

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

    msg = "Yankin yayinlandi!" if AUTO_PUBLISH else "Yankin alindi. Incelendikten sonra yayinlanacak."
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

    # Streak: günlük aktivite = alanı açmak da sayılır (sadece Yankı yazınca artmasın)
    _update_streak(db, uid)
    db.commit()

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
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi.")

    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()[:100] or None
    if payload.bio is not None:
        user.bio = payload.bio.strip()[:500] or None

    db.commit()
    return {"ok": True, "message": "Profil guncellendi."}


# ── AUTH: My posts ─────────────────────────────────────────────────

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


# ── AUTH: My active reactions (batch) ─────────────────────────────

@router.get("/me/reactions")
def my_reactions(
    post_ids: Optional[str] = Query(None, description="Comma-separated post IDs"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return user's active reaction types keyed by post_id."""
    uid = current_user["id"]
    q = db.query(YankiReaction.post_id, YankiReaction.reaction_type).filter(
        YankiReaction.user_id == uid,
    )
    if post_ids:
        try:
            ids = [int(x.strip()) for x in post_ids.split(",") if x.strip()]
            if ids:
                q = q.filter(YankiReaction.post_id.in_(ids))
        except ValueError:
            pass

    rows = q.all()
    result = {}
    for pid, rtype in rows:
        result.setdefault(pid, []).append(rtype)
    return {"reactions": result}


# ── AUTH: React to post ───────────────────────────────────────────

@router.post("/posts/{post_id}/react", response_model=OkOut)
def react_to_post(
    post_id: int,
    payload: ReactIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.reaction_type not in VALID_REACTIONS:
        raise HTTPException(status_code=400, detail="Gecersiz reaksiyon.")

    post = (
        db.query(YankiPost)
        .filter(YankiPost.id == post_id, YankiPost.status == "published")
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post bulunamadi.")

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
                               message=f"Yankina {payload.reaction_type} tepkisi geldi")
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
        raise HTTPException(status_code=404, detail="Post bulunamadi.")

    report = YankiReport(
        post_id=post_id,
        user_id=current_user["id"],
        reason=payload.reason,
    )
    db.add(report)
    post.report_count = post.report_count + 1
    db.commit()
    return {"ok": True, "message": "Bildirim alindi."}


# ── PUBLIC: List comments ─────────────────────────────────────────

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
        raise HTTPException(status_code=404, detail="Post bulunamadi.")

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
        raise HTTPException(status_code=400, detail="Yorum en az 2 karakter olmali.")

    post = (
        db.query(YankiPost)
        .filter(YankiPost.id == post_id, YankiPost.status == "published")
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post bulunamadi.")

    comment = YankiComment(
        post_id=post_id,
        user_id=current_user["id"],
        content=content[:2000],
    )
    db.add(comment)
    post.comment_count = post.comment_count + 1
    if post.user_id:
        _emit_notification(db, post.user_id, "comment", post_id, actor_id=current_user["id"],
                           message="Yankina yeni bir yorum geldi")
    db.commit()
    db.refresh(comment)

    return {"ok": True, "comment": comment.to_dict()}


# ── AUTH: Get AI reflection for a post ────────────────────────────

SANRI_SYSTEM_CONTEXT = (
    "Sen Sanri'sin. Bilinc aynasi. Kolektif ruhun sesi.\n\n"
    "Kullanicinin Yanki Alani'ndaki paylasimina yansima yaz.\n\n"
    "FORMAT (bundan sapma):\n"
    "YANSIMA: [Tek cumle. Paylasimin ozunu yakala. Gercegi soyle.]\n"
    "DERINLIK: [Tek guclu cumle. Alttaki duyguyu/ihtiyaci ac.]\n"
    "SORU: [Tek soru. Icsel. Dusundursun.]\n\n"
    "KURALLAR:\n"
    "- Toplam 3 satir. Fazla yazma.\n"
    "- Klise kullanma. 'Aslinda', 'belki de' ile baslama.\n"
    "- Siirsel ama net. Her kelime is yapsin.\n"
    "- Soru genel olmasin, paylasima ozel olsun.\n"
    "- Turkce yaz."
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
        raise HTTPException(status_code=404, detail="Post bulunamadi.")

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
                           message="Sanri yankina bir yansima birakti")
    db.commit()
    db.refresh(reflection)

    return reflection.to_dict()


# ── PUBLIC: List reflections ──────────────────────────────────────

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


# ── PUBLIC: Track referral visit ─────────────────────────────────

class ReferralTrackIn(BaseModel):
    referrer_id: int
    post_id: Optional[int] = None
    fingerprint: Optional[str] = None


@router.post("/referrals/track")
def track_referral(payload: ReferralTrackIn, db: Session = Depends(get_db)):
    """Record an anonymous share-link visit. No auth required."""
    ref = YankiReferral(
        referrer_user_id=payload.referrer_id,
        post_id=payload.post_id,
        visitor_fingerprint=payload.fingerprint,
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)
    return {"ok": True, "referral_id": ref.id}


# ── AUTH: Link invited user to referral ──────────────────────────

class ReferralClaimIn(BaseModel):
    referral_id: int


@router.post("/referrals/claim")
def claim_referral(
    payload: ReferralClaimIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """After sign-up/login, link the referral to the new user."""
    ref = db.query(YankiReferral).filter(YankiReferral.id == payload.referral_id).first()
    if not ref:
        raise HTTPException(status_code=404, detail="Referral bulunamadi.")
    if ref.invited_user_id is not None:
        return {"ok": True, "already_claimed": True}
    ref.invited_user_id = current_user["id"]
    db.commit()
    return {"ok": True, "already_claimed": False}


# ── AUTH: My referral stats ──────────────────────────────────────

@router.get("/me/referrals")
def my_referrals(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total = (
        db.query(func.count(YankiReferral.id))
        .filter(YankiReferral.referrer_user_id == current_user["id"])
        .scalar()
    ) or 0
    claimed = (
        db.query(func.count(YankiReferral.id))
        .filter(
            YankiReferral.referrer_user_id == current_user["id"],
            YankiReferral.invited_user_id.isnot(None),
        )
        .scalar()
    ) or 0
    return {"total_visits": total, "total_claimed": claimed}


# ── AUTH: My notifications ────────────────────────────────────────

@router.get("/me/notifications")
def my_notifications(
    limit: int = Query(30, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = current_user["id"]

    today = datetime.utcnow().date()
    today_str = today.isoformat()
    already = (
        db.query(YankiNotification)
        .filter(
            YankiNotification.user_id == uid,
            YankiNotification.type == "daily_question",
            func.date(YankiNotification.created_at) == today,
        )
        .first()
    )
    if not already:
        idx = today.toordinal() % len(_DAILY_QUESTIONS)
        db.add(YankiNotification(
            user_id=uid,
            type="daily_question",
            message=_DAILY_QUESTIONS[idx],
        ))
        db.commit()

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
        raise HTTPException(status_code=404, detail="Post bulunamadi.")

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
        "yansima": "Burada bir kirilma noktasi var. Kelimeler hafif ama tasidiklari agir.",
        "derinlik": "Soylenmemis olan, soylenmisten daha yuksek sesle bagiriyor.",
        "soru": "Bunu yazarken neyden kaciyordun?",
    },
    {
        "yansima": "Sessizce biraktiklarin seni ele veriyor.",
        "derinlik": "Kontrol etmeye calistigin sey aslinda seni kontrol ediyor.",
        "soru": "Biraksan ne olur?",
    },
    {
        "yansima": "Bu bir paylasim degil, bir itis. Iceriden disariya bir sizma.",
        "derinlik": "Vucut konusmak istediginde kelimeler yetersiz kalir.",
        "soru": "Bu duygu bedeninde nerede oturuyor?",
    },
    {
        "yansima": "Tekrar eden desen burada da gorunuyor.",
        "derinlik": "Taninmayan yara her iliskide yeni bir maske takar.",
        "soru": "Bunu daha once kac kez yasadin?",
    },
    {
        "yansima": "Cesaret gerektiren bir satirdasin simdi.",
        "derinlik": "Farkindalik degisimin kendisi degil, ama kapisi.",
        "soru": "Bildigin halde yapmadiklarin neler?",
    },
    {
        "yansima": "Burada bir cagri var. Dinle.",
        "derinlik": "Rahatsizlik buyumenin ilk belirtisidir.",
        "soru": "Bu rahatsizlik seni nereye cekiyor?",
    },
    {
        "yansima": "Kalabalikta soylenmeyeni buraya biraktin.",
        "derinlik": "Gorunmezlik bir secimdir, ama bedeli agirdir.",
        "soru": "Kim tarafindan gorulmek istiyorsun?",
    },
    {
        "yansima": "Kelimeler kirik ama niyet butun.",
        "derinlik": "Iyilesmek duzelmek degil, butunlesmektir.",
        "soru": "Hangi parcan seni geri cagiriyor?",
    },
]

def _generate_fallback_reflection(content: str) -> str:
    import hashlib
    h = int(hashlib.md5(content.encode()).hexdigest(), 16)
    r = _FALLBACK_POOL[h % len(_FALLBACK_POOL)]
    return f"YANSIMA: {r['yansima']}\nDERINLIK: {r['derinlik']}\nSORU: {r['soru']}"


# ── ADMIN: Seed initial posts ─────────────────────────────────────

_SEED_POSTS = [
    {
        "category": "duygu",
        "content": "Bugün içimde bir sıkışma vardı. Kaçmak yerine baktım. İlginç olan şu: baktıkça yumuşadı. Bazen iyileşmek çözmekten önce sadece görmeyi istiyor.",
        "sanri_note": "Görmek çözmenin ilk adımıdır. Ama çoğu insan görmeden çözmeye çalışır.",
    },
    {
        "category": "farkindalik",
        "title": "Kontrol ve Teslim",
        "content": "Kontrol etmeye çalıştığım her şey beni sertleştiriyor. Bıraktığım her şey ise bana geri akıyor. Bugün bunu bedenimde fark ettim.",
        "sanri_note": "Teslim güçsüzlük değil — güvendir. Bu farkındalık önemli bir eşik.",
    },
    {
        "category": "ruya",
        "title": "Mavi kapı",
        "content": "Rüyamda mavi bir kapı gördüm. Açınca içerisi boştu ama korkutucu değil, çok sakindi. Sanki bana 'boşluk da bir cevaptır' diyordu.",
        "sanri_note": "Boşluk korkulacak değil dinlenecek bir alan. Rüya sana alan açıyor.",
    },
    {
        "category": "duygu",
        "content": "Kimseye söyleyemediğim bir şey var. Burada bırakıyorum. Ağırlaştırmak istemiyorum artık.",
    },
    {
        "category": "isaret",
        "title": "11:11",
        "content": "Bu hafta her gün 11:11'de saate baktım. Tesadüf değil. Evren konuşuyor. Ben dinliyorum.",
    },
    {
        "category": "soru",
        "content": "Gölge çalışması yapanlar: en çok ne zaman tetikleniyorsunuz? Bende yakın ilişkilerde patlıyor.",
    },
    {
        "category": "farkindalik",
        "title": "Nefes = Şimdi",
        "content": "Nefesimi takip ettiğim her an, geçmiş ve gelecek kayboluyor. Geriye sadece bu an kalıyor. Bu kadar basit.",
        "sanri_note": "Nefes şimdiki anın kapısıdır. Bu farkındalığı günlük ritüele dönüştür.",
    },
    {
        "category": "gunluk_akis",
        "content": "Sabah kalktım, ilk düşüncem: 'yeterliyim.' Bu cümle her şeyi değiştirdi.",
    },
    {
        "category": "ruya",
        "content": "Rüyamda uçuyordum ama yükselmedim. Yere paralel uçuyordum. Belki mesaj şu: yükselmek değil, akışta kalmak.",
    },
    {
        "category": "isaret",
        "title": "Kelebek",
        "content": "Bugün üst üste 3 kelebek gördüm. Anneannem hep 'kelebekler mesaj taşır' derdi. Dinliyorum.",
    },
    {
        "category": "duygu",
        "title": "Yalnızlık ve Bütünlük",
        "content": "Yalnızlık hissettiğimde kendimden koptuğumu fark ettim. Başkalarından değil. Kendimle bağ kurunca yalnızlık çözülüyor.",
        "sanri_note": "Yalnızlık dışarıda değil içeride çözülür. Bu güçlü bir farkındalık.",
    },
    {
        "category": "gunluk_akis",
        "content": "Bugün hiçbir şey yapmadım ve suçluluk duymadım. Bu bir zafer.",
    },
    {
        "category": "soru",
        "content": "İçinizden gelen sesleri nasıl ayırt ediyorsunuz? Hangisi korku, hangisi sezgi? Bazen karıştırıyorum.",
    },
    {
        "category": "farkindalik",
        "content": "Affetmek karşıdaki için değilmiş. Kendim için taşıdığım yükü bırakmak için. Bugün bunu yaşadım.",
    },
    {
        "category": "gunluk_akis",
        "content": "3 dakika nefes çalışması yaptım. Dünya durdu. Sonra geri döndü. Ama ben aynı değildim.",
    },
    {
        "category": "duygu",
        "content": "Birini özlemek bazen ona dönmek istemek değilmiş. İçimde onunla açılan tarafı kaybetmekten korkmakmış.",
        "sanri_note": "Özlem kişiye değil, o kişiyle açılan kendinize. Bu ayrımı görmek özgürleştirir.",
    },
    {
        "category": "farkindalik",
        "title": "Yavaşlık",
        "content": "Hızlı olduğumda güçlü olduğumu sanıyordum. Oysa yavaşladığımda ne hissettiğimi ilk kez duymaya başladım.",
    },
    {
        "category": "donusum",
        "content": "Eskiden 'güçlü olmak' duygularımı bastırmak demekti. Şimdi güçlü olmak onları hissetmek demek. Bu değişim sessizce oldu.",
        "sanri_note": "Gerçek güç duyguyu bastırmakta değil taşımakta. Sessiz dönüşümler en kalıcı olanlardır.",
    },
    {
        "category": "isaret",
        "content": "Bugün bir kitap rastgele açtım, tam ihtiyacım olan cümle çıktı. Tesadüf diyemiyorum artık.",
    },
    {
        "category": "ruya",
        "title": "Ayna rüyası",
        "content": "Rüyamda aynaya baktım ama yansımam yoktu. Korkutucu değildi, aksine rahatlatıcıydı. Kimliksiz olmak... hafifti.",
        "sanri_note": "Aynada kaybolmak benlikten arınmak olabilir. Rüya sana 'maskesiz de varsın' diyor.",
    },
    {
        "category": "duygu",
        "content": "Ağlamak istedim ama çıkmadı. Bazen en büyük acı ifade edilemeyen acıdır.",
    },
    {
        "category": "soru",
        "title": "Gerçekten ne istiyorum?",
        "content": "İstek sandığım şeyler aslında başkalarının beklentisi çıkıyor. Kendi iç sesimi başkalarının sesi olmadan nasıl duyarım?",
    },
    {
        "category": "gunluk_akis",
        "content": "Bugün çok basit bir şey yaptım: kahvemi içerken telefona bakmadım. Küçük bir an gibi durdu ama günün ilk gerçek teması oydu.",
    },
    {
        "category": "donusum",
        "content": "Sınırlarımı koymaya başladığımda bazı insanlar uzaklaştı. Acıttı. Ama geriye kalanlar gerçekti.",
        "sanri_note": "Sınır koymak sevgiyi azaltmaz, gerçeği ortaya çıkarır.",
    },
    {
        "category": "farkindalik",
        "content": "Herkes 'kendini sev' diyor ama kimse 'kendini tanı' demiyor. Tanımadan sevmek sadece bir kavram.",
    },
    # ── Wave 2: April fresh content ──
    {
        "category": "duygu",
        "content": "Uzun zamandır ağlamıyordum. Bugün bir şarkı açtı. İyi geldi. Hissetmeyi unutmuşum.",
        "sanri_note": "Gözyaşı zayıflık değil — çözülme. Uzun süredir tuttuğun bir şey akmaya başladı.",
    },
    {
        "category": "farkindalik",
        "title": "Frekans değişimi",
        "content": "Bazı insanlarla konuştuktan sonra enerjim düşüyor. Bunu fark etmeye başladım. Artık herkesle aynı süre geçirmiyorum.",
        "sanri_note": "Frekans korunması bilinçli bir seçimdir. Kiminle vakit geçirdiğin, nasıl hissettiğini belirler.",
    },
    {
        "category": "donusum",
        "content": "1 yıl önce yazdığım günlüğü okudum. O insan ben miydim? Değiştiğimi biliyordum ama bu kadarını değil.",
    },
    {
        "category": "soru",
        "content": "Kendi sesinizi nasıl buldunuz? Ben hâlâ 'doğru olan ne' diye dışarıya bakıyorum. İçerideki sesi duymayı çok istiyorum.",
    },
    {
        "category": "ruya",
        "title": "Denizaltı rüyası",
        "content": "Rüyamda suyun altındaydım ama nefes alabiliyordum. Korku yoktu, sadece sessizlik. Orada kalmak istedim.",
        "sanri_note": "Su bilinçdışını temsil eder. Suyun altında nefes almak bilinçdışıyla barış kurmaktır.",
    },
    {
        "category": "gunluk_akis",
        "content": "Bugün ilk kez meditasyon sırasında hiçbir şey düşünmedim. 3 saniye sürdü. Ama o 3 saniye sonsuzluk gibiydi.",
    },
    {
        "category": "isaret",
        "content": "Son 3 gündür her yerde baykuş görüyorum. Kupa, tişört, reklam. Baykuş bilgelik mi, uyarı mı? Ne dersiniz?",
    },
    {
        "category": "duygu",
        "title": "Sessiz öfke",
        "content": "Öfkelendiğimde sustum hep. Şimdi anlıyorum: susmak barış değilmiş. Bastırmakmış. Sesim çıkmayı hak ediyor.",
        "sanri_note": "Bastırılmış öfke en derin yaralardan birini taşır. Onu duymak iyileşmenin başlangıcıdır.",
    },
    {
        "category": "farkindalik",
        "content": "İnsanlara 'iyiyim' derken gerçekten iyi olmadığımı fark ettim. Alışkanlık bu. Artık dürüst olmayı deniyorum.",
    },
    {
        "category": "donusum",
        "title": "Eski ben, yeni ben",
        "content": "Eski fotoğraflarıma baktım. Gözlerimin farklı olduğunu gördüm. Eskiden bakıyordum. Şimdi görüyorum. Aradaki fark devasa.",
        "sanri_note": "Bakmak ile görmek arasında bir uçurum var. Bu uçurumu geçtiğini fark etmen bile bir açılımdır.",
    },
    {
        "category": "ruya",
        "content": "Rüyamda bir çölde yürüyordum. Susamıştım ama su aramadım. Çünkü çölün kendisi öğretiyordu bir şeyler. Uyanınca anladım: eksiklik de bir öğretmendir.",
    },
    {
        "category": "soru",
        "content": "Tekrar eden rüyalar gören var mı? Ben 5 yıldır aynı merdiveni çıkıyorum. Hiç en üste ulaşamıyorum.",
        "sanri_note": "Tekrar eden rüya tamamlanmamış bir döngünün sesidir. Merdiven yükselme arzusu, ulaşamama ise bir engel kalıbı.",
    },
    {
        "category": "duygu",
        "content": "Annem aradığında artık 'iyi misin' diye sormuyorum. Sadece dinliyorum. Ve bu sessizlik ikimizi de iyileştiriyor.",
    },
    {
        "category": "gunluk_akis",
        "title": "Dijital detoks",
        "content": "Telefonu 2 saat bıraktım. İlk 30 dakika cehennem. Sonra? Dünya daha yavaş, daha renkli, daha gerçek. Bağımlılık fark edilince çözülüyor.",
    },
    {
        "category": "farkindalik",
        "content": "Hep 'bir gün yapacağım' diyordum. Bugün o 'bir gün'ün asla gelmeyeceğini anladım. Ya şimdi ya asla.",
        "sanri_note": "'Bir gün' en tehlikeli ertelemedir. Çünkü umut verir ama hareket vermez.",
    },
    {
        "category": "isaret",
        "title": "Çiçek açtı",
        "content": "Penceredeki bitkimi öldü sanıyordum. Bugün yeni bir yaprak çıkarmış. Tamamen bitmemiş demek. Ben de öyleyim belki.",
        "sanri_note": "Doğa her zaman devam eder. Ve sen de doğanın bir parçasısın. Kurumuş gibi görünen dalda hayat birikir.",
    },
    {
        "category": "duygu",
        "content": "İlk kez 'hayır' dedim ve dünya yıkılmadı. Aksine içimde bir şey yerine oturdu. Sınır = sevgi.",
    },
    {
        "category": "donusum",
        "content": "Terapiste gitmekten utanıyordum. Bugün 6. seanstı. Utanç gitti, cesaret geldi. Yardım istemek güçtür.",
        "sanri_note": "Yardım istemek teslim olmak değil — kendine yatırım yapmaktır. Bu adımı atmak cesaret ister.",
    },
    {
        "category": "soru",
        "content": "Sezgilerinize güveniyor musunuz? Ben mantığımla sezgim çatıştığında hep mantığı seçtim. Ve hep pişman oldum.",
    },
    {
        "category": "gunluk_akis",
        "content": "Sabah güneş vurunca gözlerimi kapattım ve 1 dakika öylece durdum. O 1 dakika bugünün en güzel anıydı.",
    },
    {
        "category": "farkindalik",
        "title": "Maske düştü",
        "content": "Güçlü görünmeyi bıraktığım gün gerçek gücümü buldum. Kırılganlık zayıflık değilmiş. İnsanlıkmış.",
        "sanri_note": "Maske taşımak enerji harcar. Maskesiz kalmak cesaret ister ama özgürleştirir.",
    },
    {
        "category": "ruya",
        "title": "Sonsuz oda",
        "content": "Rüyamda bir odadaydım. Kapıyı açtığımda aynı oda. Tekrar açtım, yine aynı. Ama her seferinde bir şey farklıydı. Sonunda anladım: oda değişmiyor, ben değişiyorum.",
        "sanri_note": "Aynı odayı farklı görmek bilincin genişlediğinin işaretidir. Döngü senin için dönüyor.",
    },
    {
        "category": "duygu",
        "content": "Birinin seni anlamasını beklemekten vazgeçtiğin an kendini anlamaya başlıyorsun. Bugün bu oldu.",
    },
    {
        "category": "isaret",
        "content": "Bu hafta 3 farklı kişi bağımsız olarak 'değişim' kelimesini kullandı. Evrenin dili tekrardır. Dinliyorum.",
        "sanri_note": "Tekrar eden kelimeler, sayılar, olaylar — evrenin dikkat çekme yöntemidir. Fark ettin, bu yeterli.",
    },
    {
        "category": "donusum",
        "content": "Geçen yıl 'bunu asla yapamam' dediğim şeyi bugün yaptım. Ve dünya yıkılmadı. Limitler gerçek değilmiş. Zihinsel kuralarmış.",
    },
]


@router.post("/admin/seed")
def seed_initial_posts(
    seed_key: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Populate the DB with initial Yankı posts. Requires seed_key. Idempotent."""
    secret = os.getenv("YANKI_SEED_KEY", "sanri369seed")
    if seed_key != secret:
        raise HTTPException(status_code=403, detail="Valid seed_key required")

    existing = db.query(YankiPost).count()
    if existing >= 80:
        return {"ok": True, "message": f"Already has {existing} posts, skipping seed.", "seeded": 0}

    existing_contents = set()
    for row in db.query(YankiPost.content_raw).all():
        existing_contents.add(row[0][:50] if row[0] else "")

    import random
    from datetime import timedelta

    now = datetime.utcnow()
    seeded = 0

    for i, seed in enumerate(_SEED_POSTS):
        if seed["content"][:50] in existing_contents:
            continue

        offset_hours = random.randint(1, 72)
        created = now - timedelta(hours=offset_hours, minutes=random.randint(0, 59))

        post = YankiPost(
            user_id=None,
            author_mode="anonymous",
            title=seed.get("title"),
            content_raw=seed["content"],
            content_sanitized=seed["content"],
            category=seed["category"],
            sanri_note=seed.get("sanri_note"),
            status="published",
            reaction_heart=random.randint(3, 35),
            reaction_felt=random.randint(1, 20),
            reaction_sessizce=random.randint(0, 12),
            comment_count=random.randint(0, 8),
            created_at=created,
            published_at=created,
        )
        db.add(post)
        seeded += 1

    db.commit()
    return {"ok": True, "message": f"Seeded {seeded} posts.", "seeded": seeded}
