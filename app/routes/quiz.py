"""
Onboarding quiz — lead capture, scoring, email dispatch.
POST /quiz/submit  →  saves quiz result + sends result email
GET  /quiz/stats   →  admin stats
"""
import logging
import json
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.services.email_service import send_email, _wrap_email_layout

logger = logging.getLogger("quiz")
router = APIRouter(prefix="/quiz", tags=["quiz"])

# ─── Ensure table ─────────────────────────────────────────────────

_table_ready = False

def _ensure_table(db: Session):
    global _table_ready
    if _table_ready:
        return
    try:
        is_pg = "postgresql" in str(db.bind.url) if hasattr(db, "bind") and db.bind else False
        if is_pg:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS quiz_submissions (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(320) NOT NULL,
                    answers_json TEXT,
                    primary_theme VARCHAR(64),
                    secondary_theme VARCHAR(64),
                    recommended_area VARCHAR(128),
                    scores_json TEXT,
                    source VARCHAR(64) DEFAULT 'direct',
                    utm_campaign VARCHAR(128) DEFAULT '',
                    utm_medium VARCHAR(128) DEFAULT '',
                    email_sent BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
        else:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS quiz_submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    answers_json TEXT,
                    primary_theme TEXT,
                    secondary_theme TEXT,
                    recommended_area TEXT,
                    scores_json TEXT,
                    source TEXT DEFAULT 'direct',
                    utm_campaign TEXT DEFAULT '',
                    utm_medium TEXT DEFAULT '',
                    email_sent INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """))
        db.commit()
        _table_ready = True
    except Exception as e:
        logger.warning("quiz table creation (might already exist): %s", e)
        db.rollback()
        _table_ready = True


# ─── Theme display mapping ────────────────────────────────────────

THEME_LABELS = {
    "dongu": "Tekrar Eden Döngüler",
    "baskilama": "Bastırılan Katman",
    "farkindalik": "Uyanış Frekansı",
    "yeterlilik": "Yeterlilik Döngüsü",
    "arayis": "Anlam Arayışı",
    "kiyaslama": "Kıyaslama Döngüsü",
    "belirsizlik": "Belirsizlik Alanı",
    "anlasilma": "Anlaşılma İhtiyacı",
    "kariyer": "Akış Tıkanıklığı",
    "kimlik": "Kimlik Arayışı",
    "ozgur": "Özgür Akış",
}

AREA_LABELS = {
    "rol-okuma": "Rol Okuma",
    "sanriya-sor": "Anlaşılma Alanı",
    "frekans": "Frekans Alanı",
    "/": "Anlaşılma Alanı",
}

AREA_URLS = {
    "rol-okuma": "https://asksanri.com/rol-okuma",
    "sanriya-sor": "https://asksanri.com/sanriya-sor",
    "frekans": "https://asksanri.com/frekans",
    "/": "https://asksanri.com/",
}


# ─── Email builder ────────────────────────────────────────────────

def _build_result_email(primary_theme: str, recommended_area: str) -> str:
    theme_label = THEME_LABELS.get(primary_theme, primary_theme)
    area_label = AREA_LABELS.get(recommended_area, "Anlaşılma Alanı")
    area_url = AREA_URLS.get(recommended_area, "https://asksanri.com/")

    inner = f"""
    <tr><td align="center" style="padding-bottom:20px;">
        <span style="color:#ffffff;font-size:22px;font-weight:800;">Farkındalık Testin Hazır</span>
    </td></tr>
    <tr><td style="padding-bottom:20px;">
        <p style="color:rgba(255,255,255,0.72);font-size:15px;line-height:1.7;margin:0;">
            Merhaba,<br/><br/>
            Sanrı farkındalık testini tamamladın. İşte senin sonucun:
        </p>
    </td></tr>
    <tr><td style="padding-bottom:20px;">
        <div style="background:rgba(124,247,216,0.06);border:1px solid rgba(124,247,216,0.18);border-radius:16px;padding:20px 24px;text-align:center;">
            <p style="color:rgba(124,247,216,0.55);font-size:11px;letter-spacing:2px;text-transform:uppercase;margin:0 0 8px;">BASKIN DÖNGÜN</p>
            <p style="color:#7cf7d8;font-size:22px;font-weight:800;margin:0 0 12px;">{theme_label}</p>
            <p style="color:rgba(255,255,255,0.5);font-size:13px;margin:0;">Sanrı sana <strong style="color:#e8e4f0;">{area_label}</strong> ile başlamayı öneriyor.</p>
        </div>
    </td></tr>
    <tr><td style="padding-bottom:20px;">
        <p style="color:rgba(255,255,255,0.60);font-size:14px;line-height:1.7;margin:0;">
            Bu sonuç, verdiğin cevaplara göre en baskın frekansını yansıtıyor.
            Sanrı seni yargılamaz — sadece görünmeyeni görünür kılar.
        </p>
    </td></tr>
    <tr><td align="center" style="padding-bottom:20px;">
        <a href="{area_url}" style="display:inline-block;padding:14px 40px;background:linear-gradient(135deg,#c8a0ff,#a07aff);color:#07080d;font-weight:700;font-size:15px;border-radius:12px;text-decoration:none;">
            {area_label}'na Geç
        </a>
    </td></tr>
    <tr><td style="padding-bottom:8px;">
        <p style="color:rgba(255,255,255,0.35);font-size:12px;line-height:1.6;margin:0;text-align:center;">
            <a href="https://asksanri.com/rol-okuma" style="color:#bb86fc;text-decoration:none;">Rol Okuma</a> ·
            <a href="https://asksanri.com/frekans" style="color:#bb86fc;text-decoration:none;">Frekans Alanı</a> ·
            <a href="https://asksanri.com/sanriya-sor" style="color:#bb86fc;text-decoration:none;">Sanrı'ya Sor</a>
        </p>
    </td></tr>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#07080d;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#07080d;padding:40px 20px;"><tr><td align="center">
<table width="500" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,rgba(169,112,255,0.12),rgba(94,59,255,0.06));border:1px solid rgba(169,112,255,0.2);border-radius:24px;padding:44px 36px;">
<tr><td align="center" style="padding-bottom:28px;"><span style="color:#b388ff;font-size:28px;font-weight:900;letter-spacing:2px;">SANRI</span></td></tr>
{inner}
<tr><td align="center" style="padding-top:16px;"><p style="color:rgba(255,255,255,0.3);font-size:11px;margin:0;">Sanrı — Bilinç ve Anlam Zekası<br/>asksanri.com</p></td></tr>
</table></td></tr></table></body></html>"""


# ─── Models ───────────────────────────────────────────────────────

class QuizSubmitIn(BaseModel):
    email: str
    answers: dict
    primary_theme: str
    secondary_theme: Optional[str] = ""
    recommended_area: str
    scores: Optional[dict] = None
    source: Optional[str] = "direct"
    utm_campaign: Optional[str] = ""
    utm_medium: Optional[str] = ""


# ─── Endpoint ─────────────────────────────────────────────────────

@router.post("/submit")
def submit_quiz(body: QuizSubmitIn, db: Session = Depends(get_db)):
    _ensure_table(db)

    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Geçerli bir e-posta adresi gerekiyor.")

    try:
        db.execute(text("""
            INSERT INTO quiz_submissions
                (email, answers_json, primary_theme, secondary_theme,
                 recommended_area, scores_json, source, utm_campaign, utm_medium)
            VALUES
                (:email, :answers, :pt, :st, :area, :scores, :src, :camp, :med)
        """), {
            "email": email,
            "answers": json.dumps(body.answers, ensure_ascii=False),
            "pt": body.primary_theme,
            "st": body.secondary_theme or "",
            "area": body.recommended_area,
            "scores": json.dumps(body.scores or {}, ensure_ascii=False),
            "src": body.source or "direct",
            "camp": body.utm_campaign or "",
            "med": body.utm_medium or "",
        })
        db.commit()
    except Exception as e:
        logger.error("quiz insert fail: %s", e)
        db.rollback()

    email_sent = False
    try:
        html = _build_result_email(body.primary_theme, body.recommended_area)
        email_sent = send_email(email, "Sanrı — Farkındalık Test Sonucun", html)
        if email_sent:
            try:
                db.execute(text(
                    "UPDATE quiz_submissions SET email_sent = TRUE WHERE email = :e ORDER BY created_at DESC LIMIT 1"
                ), {"e": email})
                db.commit()
            except Exception:
                db.rollback()
    except Exception as e:
        logger.warning("quiz result email fail: %s", e)

    return {"ok": True, "email_sent": email_sent}


@router.get("/stats")
def quiz_stats(db: Session = Depends(get_db)):
    """Admin-only basic stats."""
    _ensure_table(db)
    try:
        total = db.execute(text("SELECT COUNT(*) FROM quiz_submissions")).scalar() or 0
        themes = db.execute(text(
            "SELECT primary_theme, COUNT(*) as cnt FROM quiz_submissions GROUP BY primary_theme ORDER BY cnt DESC"
        )).fetchall()
        areas = db.execute(text(
            "SELECT recommended_area, COUNT(*) as cnt FROM quiz_submissions GROUP BY recommended_area ORDER BY cnt DESC"
        )).fetchall()
        recent = db.execute(text(
            "SELECT email, primary_theme, recommended_area, created_at FROM quiz_submissions ORDER BY created_at DESC LIMIT 10"
        )).fetchall()
        return {
            "total": total,
            "themes": [{"theme": r[0], "count": r[1]} for r in themes],
            "areas": [{"area": r[0], "count": r[1]} for r in areas],
            "recent": [{"email": r[0], "theme": r[1], "area": r[2], "at": str(r[3])} for r in recent],
        }
    except Exception as e:
        logger.error("quiz stats error: %s", e)
        return {"total": 0, "themes": [], "areas": [], "recent": []}


def _table_exists(db, name: str) -> bool:
    try:
        db.execute(text(f"SELECT 1 FROM {name} LIMIT 0"))
        return True
    except Exception:
        db.rollback()
        return False


def _is_pg(db) -> bool:
    try:
        url = str(db.bind.url) if hasattr(db, "bind") and db.bind else ""
        return "postgresql" in url
    except Exception:
        return False


@router.get("/admin/all-leads")
def all_leads(
    limit: int = 200,
    offset: int = 0,
    search: str = "",
    db: Session = Depends(get_db),
):
    """Unified view of ALL collected emails across every source."""
    _ensure_table(db)

    table_queries = {
        "users": "SELECT email, name, 'registered' as source, '' as page, '' as theme, created_at FROM users WHERE email IS NOT NULL AND email != ''",
        "email_leads": "SELECT email, name, COALESCE(source,'popup') as source, COALESCE(page,'') as page, '' as theme, created_at FROM email_leads WHERE email IS NOT NULL AND email != ''",
        "quiz_submissions": "SELECT email, '' as name, 'quiz' as source, COALESCE(recommended_area,'') as page, COALESCE(primary_theme,'') as theme, created_at FROM quiz_submissions WHERE email IS NOT NULL AND email != ''",
        "shopier_purchases": "SELECT email, '' as name, 'purchase' as source, COALESCE(content_id,'') as page, '' as theme, created_at FROM shopier_purchases WHERE email IS NOT NULL AND email != ''",
    }

    parts = []
    for tbl, sql_part in table_queries.items():
        if _table_exists(db, tbl):
            parts.append(sql_part)

    if not parts:
        return {"total": 0, "leads": [], "sources": {}}

    union_sql = " UNION ALL ".join(parts)
    is_pg = _is_pg(db)
    group_concat_fn = "STRING_AGG(DISTINCT source, ',')" if is_pg else "GROUP_CONCAT(DISTINCT source)"

    where_clause = ""
    params = {"lim": limit, "off": offset}
    if search:
        where_clause = " WHERE email LIKE :q "
        params["q"] = f"%{search}%"

    sql = f"""
        SELECT email, MAX(name) as name,
               {group_concat_fn} as sources,
               MAX(page) as page, MAX(theme) as theme,
               MIN(created_at) as first_seen, MAX(created_at) as last_seen,
               COUNT(*) as touchpoints
        FROM ({union_sql}) AS combined
        {where_clause}
        GROUP BY email
        ORDER BY last_seen DESC
        LIMIT :lim OFFSET :off
    """

    count_sql = f"""
        SELECT COUNT(DISTINCT email) FROM ({union_sql}) AS combined {where_clause}
    """

    try:
        total = db.execute(text(count_sql), params).scalar() or 0
        rows = db.execute(text(sql), params).fetchall()

        leads = []
        for r in rows:
            leads.append({
                "email": r[0],
                "name": r[1] or "",
                "sources": r[2] or "",
                "page": r[3] or "",
                "theme": r[4] or "",
                "first_seen": str(r[5]) if r[5] else "",
                "last_seen": str(r[6]) if r[6] else "",
                "touchpoints": r[7] or 1,
            })

        src_sql = f"""
            SELECT source, COUNT(DISTINCT email) as cnt
            FROM ({union_sql}) AS combined
            GROUP BY source ORDER BY cnt DESC
        """
        src_rows = db.execute(text(src_sql)).fetchall()
        sources = {r[0]: r[1] for r in src_rows}

        return {"total": total, "leads": leads, "sources": sources}
    except Exception as e:
        logger.error("all-leads query error: %s", e)
        return {"total": 0, "leads": [], "sources": {}, "error": str(e)}


@router.get("/admin/export-emails")
def export_emails(db: Session = Depends(get_db)):
    """Return all unique emails as a simple list for export."""
    _ensure_table(db)
    parts = []
    for tbl in ["users", "email_leads", "quiz_submissions", "shopier_purchases"]:
        if _table_exists(db, tbl):
            parts.append(f"SELECT DISTINCT email FROM {tbl} WHERE email IS NOT NULL AND email != ''")
    if not parts:
        return {"emails": [], "total": 0}
    union = " UNION ".join(parts)
    rows = db.execute(text(f"SELECT DISTINCT email FROM ({union}) AS all_emails ORDER BY email")).fetchall()
    emails = [r[0] for r in rows]
    return {"emails": emails, "total": len(emails)}
