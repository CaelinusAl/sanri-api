"""
Admin Session & Retention Analytics — Oturum süresi, günlük aktif kullanıcı,
retention, ekran bazlı geçiş ve session heatmap.

events tablosundaki session_start / heartbeat / screen_view / session_end
kayıtlarını kullanır. meta alanı: { session_id, screen, duration_sec }.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.db import get_db
from app.routes.admin import _require_jwt

router = APIRouter(prefix="/admin", tags=["admin-sessions"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════
# SESSION OVERVIEW
# ═══════════════════════════════════════════════

@router.get("/session-stats")
def session_stats(
    period: str = Query(default="7d"),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    """Oturum istatistikleri: ortalama süre, günlük aktif, session sayısı."""
    days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}.get(period, 7)
    since = _utc_now() - timedelta(days=days)

    # Total sessions
    total_sessions = int(
        db.execute(
            sa_text("SELECT COUNT(*) FROM events WHERE action = 'session_start' AND created_at >= :s"),
            {"s": since},
        ).scalar() or 0
    )

    # Unique users with sessions
    unique_session_users = int(
        db.execute(
            sa_text("""
                SELECT COUNT(DISTINCT COALESCE(user_id, meta->>'session_id'))
                FROM events WHERE action = 'session_start' AND created_at >= :s
            """),
            {"s": since},
        ).scalar() or 0
    )

    # Average session duration (from heartbeat events with duration_sec)
    avg_duration = float(
        db.execute(
            sa_text("""
                SELECT COALESCE(AVG((meta->>'duration_sec')::float), 0)
                FROM events
                WHERE action = 'heartbeat'
                  AND meta->>'duration_sec' IS NOT NULL
                  AND created_at >= :s
            """),
            {"s": since},
        ).scalar() or 0
    )

    # Daily Active Users (DAU)
    dau_rows = db.execute(
        sa_text("""
            SELECT DATE(created_at) AS day,
                   COUNT(DISTINCT COALESCE(user_id, meta->>'session_id')) AS cnt
            FROM events
            WHERE action IN ('session_start', 'screen_view', 'page_view', 'message_sent')
              AND created_at >= :s
            GROUP BY DATE(created_at)
            ORDER BY day
        """),
        {"s": since},
    ).mappings().all()

    # Sessions per day
    sessions_daily = db.execute(
        sa_text("""
            SELECT DATE(created_at) AS day, COUNT(*) AS cnt
            FROM events
            WHERE action = 'session_start' AND created_at >= :s
            GROUP BY DATE(created_at)
            ORDER BY day
        """),
        {"s": since},
    ).mappings().all()

    # Screen time breakdown (from time_spent events)
    screen_time = db.execute(
        sa_text("""
            SELECT meta->>'screen' AS screen,
                   COUNT(*) AS visits,
                   COALESCE(SUM((meta->>'seconds')::float), 0) AS total_sec,
                   COALESCE(AVG((meta->>'seconds')::float), 0) AS avg_sec
            FROM events
            WHERE action = 'time_spent'
              AND meta->>'screen' IS NOT NULL
              AND created_at >= :s
            GROUP BY meta->>'screen'
            ORDER BY total_sec DESC
            LIMIT 25
        """),
        {"s": since},
    ).mappings().all()

    # Top screens by page views
    top_screens = db.execute(
        sa_text("""
            SELECT COALESCE(meta->>'screen', meta->>'page', domain) AS screen,
                   COUNT(*) AS views
            FROM events
            WHERE action IN ('screen_view', 'page_view')
              AND created_at >= :s
            GROUP BY screen
            ORDER BY views DESC
            LIMIT 20
        """),
        {"s": since},
    ).mappings().all()

    # Hourly distribution (session starts)
    hourly = db.execute(
        sa_text("""
            SELECT EXTRACT(HOUR FROM created_at)::int AS hour, COUNT(*) AS cnt
            FROM events
            WHERE action IN ('session_start', 'screen_view', 'page_view')
              AND created_at >= :s
            GROUP BY hour
            ORDER BY hour
        """),
        {"s": since},
    ).mappings().all()

    return {
        "period": period,
        "total_sessions": total_sessions,
        "unique_session_users": unique_session_users,
        "avg_session_duration_sec": round(avg_duration, 1),
        "avg_session_duration_min": round(avg_duration / 60, 1) if avg_duration else 0,
        "dau": [{"day": str(r["day"]), "count": int(r["cnt"])} for r in dau_rows],
        "sessions_daily": [{"day": str(r["day"]), "count": int(r["cnt"])} for r in sessions_daily],
        "screen_time": [
            {
                "screen": r["screen"],
                "visits": int(r["visits"]),
                "total_sec": round(float(r["total_sec"]), 1),
                "avg_sec": round(float(r["avg_sec"]), 1),
            }
            for r in screen_time
        ],
        "top_screens": [{"screen": r["screen"] or "unknown", "views": int(r["views"])} for r in top_screens],
        "hourly_distribution": [{"hour": int(r["hour"]), "count": int(r["cnt"])} for r in hourly],
    }


# ═══════════════════════════════════════════════
# RETENTION
# ═══════════════════════════════════════════════

@router.get("/retention")
def retention(
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    """Haftalık retention: kayıt sonrası 1., 7., 14., 30. gün geri dönüş."""
    now = _utc_now()
    cohort_start = now - timedelta(days=60)

    retention_data = []
    for day_offset in [1, 3, 7, 14, 30]:
        try:
            r = db.execute(
                sa_text("""
                    WITH cohort AS (
                        SELECT id, created_at::date AS reg_date
                        FROM users
                        WHERE created_at >= :cs
                    ),
                    returned AS (
                        SELECT DISTINCT c.id
                        FROM cohort c
                        JOIN events e ON e.user_id = c.id::text
                        WHERE e.created_at::date >= (c.reg_date + :offset)
                          AND e.created_at::date < (c.reg_date + :offset + 1)
                    )
                    SELECT
                        (SELECT COUNT(*) FROM cohort) AS cohort_size,
                        (SELECT COUNT(*) FROM returned) AS returned_count
                """),
                {"cs": cohort_start, "offset": day_offset},
            ).mappings().first()
            cohort_size = int(r["cohort_size"]) if r else 0
            returned_count = int(r["returned_count"]) if r else 0
            rate = round((returned_count / max(cohort_size, 1)) * 100, 1)
            retention_data.append({
                "day": day_offset,
                "label": f"D{day_offset}",
                "cohort_size": cohort_size,
                "returned": returned_count,
                "rate_pct": rate,
            })
        except Exception:
            retention_data.append({"day": day_offset, "label": f"D{day_offset}", "cohort_size": 0, "returned": 0, "rate_pct": 0})

    # Weekly cohort sizes
    weekly_cohorts = []
    for w in range(8):
        ws = now - timedelta(weeks=w + 1)
        we = now - timedelta(weeks=w)
        try:
            cnt = int(
                db.execute(
                    sa_text("SELECT COUNT(*) FROM users WHERE created_at >= :ws AND created_at < :we"),
                    {"ws": ws, "we": we},
                ).scalar() or 0
            )
        except Exception:
            cnt = 0
        weekly_cohorts.append({
            "week_ago": w + 1,
            "label": f"{(w+1)} hafta önce",
            "new_users": cnt,
        })

    # Churn indicator: users who registered but had 0 events in last 14 days
    try:
        churn_14d = int(
            db.execute(
                sa_text("""
                    SELECT COUNT(*) FROM users u
                    WHERE u.created_at < :cutoff
                      AND NOT EXISTS (
                          SELECT 1 FROM events e
                          WHERE e.user_id = u.id::text
                            AND e.created_at >= :since
                      )
                """),
                {"cutoff": now - timedelta(days=14), "since": now - timedelta(days=14)},
            ).scalar() or 0
        )
    except Exception:
        churn_14d = 0

    return {
        "retention": retention_data,
        "weekly_cohorts": weekly_cohorts,
        "churn_14d_inactive": churn_14d,
    }


# ═══════════════════════════════════════════════
# FAZ 1 — ÜRÜN METRİKLERİ
# Strateji: ilk 100 kullanıcı, davranış gözlemi.
# Takip: ilk soru soruldu mu · sekme/günlük kullanımı · tekrar gelme ·
#        ortalama konuşma süresi · en çok kullanılan sekme.
# Anonim kimlik: COALESCE(user_id, meta->>'session_id').
# ═══════════════════════════════════════════════

@router.get("/faz1")
def faz1_metrics(
    period: str = Query(default="30d"),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "all": 3650}.get(period, 30)
    since = _utc_now() - timedelta(days=days)
    ident = "COALESCE(user_id, meta->>'session_id')"

    def scalar(sql: str) -> float:
        try:
            return float(db.execute(sa_text(sql), {"s": since}).scalar() or 0)
        except Exception:
            return 0.0

    # 1) Aktivasyon: ilk soruyu soran tekil kullanıcı / toplam açan tekil kullanıcı
    openers = int(scalar(
        f"SELECT COUNT(DISTINCT {ident}) FROM events WHERE action IN ('app_open','session_start') AND created_at >= :s"
    ))
    asked = int(scalar(
        f"SELECT COUNT(DISTINCT {ident}) FROM events WHERE action = 'first_question_asked' AND created_at >= :s"
    ))
    activation_rate = round((asked / max(openers, 1)) * 100, 1)

    # 2) Tekrar gelme: app_open içinde is_returning = true olan tekil kullanıcı
    returning_users = int(scalar(
        f"SELECT COUNT(DISTINCT {ident}) FROM events WHERE action = 'app_open' AND meta->>'is_returning' = 'true' AND created_at >= :s"
    ))
    return_rate = round((returning_users / max(openers, 1)) * 100, 1)

    # 3) Ortalama konuşma süresi + ortalama mesaj sayısı (conversation_ended)
    avg_convo_sec = scalar(
        "SELECT COALESCE(AVG((meta->>'duration_sec')::float),0) FROM events WHERE action = 'conversation_ended' AND meta->>'duration_sec' IS NOT NULL AND created_at >= :s"
    )
    avg_msg_per_convo = scalar(
        "SELECT COALESCE(AVG((meta->>'message_count')::float),0) FROM events WHERE action = 'conversation_ended' AND meta->>'message_count' IS NOT NULL AND created_at >= :s"
    )
    total_convos = int(scalar(
        "SELECT COUNT(*) FROM events WHERE action = 'conversation_ended' AND created_at >= :s"
    ))

    # 4) Sekme/bağlam kullanımı (message_sent → meta.ctx): home/journal/dream/relationship
    ctx_rows = db.execute(
        sa_text("""
            SELECT COALESCE(meta->>'ctx','bilinmiyor') AS ctx, COUNT(*) AS messages
            FROM events
            WHERE action = 'message_sent' AND created_at >= :s
            GROUP BY ctx ORDER BY messages DESC
        """),
        {"s": since},
    ).mappings().all()

    # 5) En çok kullanılan sekme (screen_view → meta.screen)
    tab_rows = db.execute(
        sa_text("""
            SELECT COALESCE(meta->>'screen', domain, 'bilinmiyor') AS screen, COUNT(*) AS views
            FROM events
            WHERE action = 'screen_view' AND created_at >= :s
            GROUP BY screen ORDER BY views DESC LIMIT 15
        """),
        {"s": since},
    ).mappings().all()

    total_messages = int(scalar(
        "SELECT COUNT(*) FROM events WHERE action = 'message_sent' AND created_at >= :s"
    ))

    # Özellik/sekme açılışları (dream_open, relationship_open, journal_open, home_open).
    open_rows = db.execute(
        sa_text("""
            SELECT action, COUNT(*) AS cnt
            FROM events
            WHERE action IN ('home_open','journal_open','dream_open','relationship_open')
              AND created_at >= :s
            GROUP BY action ORDER BY cnt DESC
        """),
        {"s": since},
    ).mappings().all()

    return {
        "period": period,
        "activation": {
            "users_opened": openers,
            "users_asked_first_question": asked,
            "activation_rate_pct": activation_rate,
        },
        "retention": {
            "returning_users": returning_users,
            "return_rate_pct": return_rate,
        },
        "conversation": {
            "total_conversations": total_convos,
            "total_messages": total_messages,
            "avg_duration_sec": round(avg_convo_sec, 1),
            "avg_duration_min": round(avg_convo_sec / 60, 1) if avg_convo_sec else 0,
            "avg_messages_per_conversation": round(avg_msg_per_convo, 1),
        },
        "by_context": [{"ctx": r["ctx"], "messages": int(r["messages"])} for r in ctx_rows],
        "top_tabs": [{"screen": r["screen"], "views": int(r["views"])} for r in tab_rows],
        "feature_opens": [
            {"feature": r["action"].replace("_open", ""), "opens": int(r["cnt"])}
            for r in open_rows
        ],
    }


# ═══════════════════════════════════════════════
# FAZ 2 — YAŞAM TEMASI DAĞILIMI
# message_theme event'lerini (meta.theme) raporlar.
# ═══════════════════════════════════════════════

_THEME_LABELS = {
    "ask": "Aşk",
    "ayrilik": "Ayrılık",
    "ruya": "Rüya",
    "kaygi": "Kaygı",
    "kararsizlik": "Kararsızlık",
    "hayat_amaci": "Hayat Amacı",
    "para": "Para",
    "aile": "Aile",
    "yalnizlik": "Yalnızlık",
    "ozdeger": "Öz Değer",
    "diger": "Diğer",
}


@router.get("/themes")
def theme_distribution(
    period: str = Query(default="30d"),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    """En çok konuşulan yaşam temaları + günlük trend."""
    days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "all": 3650}.get(period, 30)
    since = _utc_now() - timedelta(days=days)

    rows = db.execute(
        sa_text("""
            SELECT COALESCE(meta->>'theme','diger') AS theme, COUNT(*) AS cnt
            FROM events
            WHERE action = 'message_theme' AND created_at >= :s
            GROUP BY theme ORDER BY cnt DESC
        """),
        {"s": since},
    ).mappings().all()

    total = sum(int(r["cnt"]) for r in rows) or 1

    distribution = [
        {
            "theme": r["theme"],
            "label": _THEME_LABELS.get(r["theme"], r["theme"]),
            "count": int(r["cnt"]),
            "pct": round(int(r["cnt"]) / total * 100, 1),
        }
        for r in rows
    ]

    # Günlük tema trendi (ısı haritası / çizgi için).
    trend = db.execute(
        sa_text("""
            SELECT DATE(created_at) AS day,
                   COALESCE(meta->>'theme','diger') AS theme,
                   COUNT(*) AS cnt
            FROM events
            WHERE action = 'message_theme' AND created_at >= :s
            GROUP BY day, theme ORDER BY day
        """),
        {"s": since},
    ).mappings().all()

    return {
        "period": period,
        "total_tagged_messages": sum(int(r["cnt"]) for r in rows),
        "distribution": distribution,
        "top_theme": distribution[0] if distribution else None,
        "trend": [
            {"day": str(r["day"]), "theme": r["theme"], "count": int(r["cnt"])}
            for r in trend
        ],
    }


# ═══════════════════════════════════════════════
# GATE 33 — DERİNLEŞME DÖNÜŞÜM HUNİSİ
# deepen_offer_shown vs deepen_offer_accepted (tema bazında).
# ═══════════════════════════════════════════════

@router.get("/gate33")
def gate33_funnel(
    period: str = Query(default="30d"),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    """Tema bazında derinleşme davetinin gösterim / kabul / dönüşüm oranı."""
    days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "all": 3650}.get(period, 30)
    since = _utc_now() - timedelta(days=days)

    rows = db.execute(
        sa_text("""
            SELECT COALESCE(meta->>'theme','diger') AS theme,
                   SUM(CASE WHEN action = 'deepen_offer_shown' THEN 1 ELSE 0 END) AS shown,
                   SUM(CASE WHEN action = 'deepen_offer_accepted' THEN 1 ELSE 0 END) AS accepted
            FROM events
            WHERE action IN ('deepen_offer_shown','deepen_offer_accepted')
              AND created_at >= :s
            GROUP BY theme
            ORDER BY shown DESC
        """),
        {"s": since},
    ).mappings().all()

    by_theme = []
    total_shown = 0
    total_accepted = 0
    for r in rows:
        shown = int(r["shown"] or 0)
        accepted = int(r["accepted"] or 0)
        total_shown += shown
        total_accepted += accepted
        by_theme.append({
            "theme": r["theme"],
            "label": _THEME_LABELS.get(r["theme"], r["theme"]),
            "shown": shown,
            "accepted": accepted,
            "conversion_pct": round(accepted / shown * 100, 1) if shown else 0,
        })

    return {
        "period": period,
        "total_offers_shown": total_shown,
        "total_offers_accepted": total_accepted,
        "overall_conversion_pct": round(total_accepted / total_shown * 100, 1) if total_shown else 0,
        "by_theme": by_theme,
    }


# ═══════════════════════════════════════════════
# USER JOURNEY DETAIL
# ═══════════════════════════════════════════════

@router.get("/user-journey")
def user_journey(
    user_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
    admin=Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    """Tek bir kullanıcının event geçmişi (yolculuk haritası)."""
    rows = db.execute(
        sa_text("""
            SELECT id, action, domain, meta, created_at
            FROM events
            WHERE user_id = :uid
            ORDER BY created_at DESC
            LIMIT :lim
        """),
        {"uid": user_id, "lim": limit},
    ).mappings().all()

    user_info = db.execute(
        sa_text("SELECT id, email, role, is_premium, email_verified, created_at FROM users WHERE id = :uid LIMIT 1"),
        {"uid": int(user_id) if user_id.isdigit() else 0},
    ).mappings().first()

    return {
        "user": dict(user_info) if user_info else None,
        "event_count": len(rows),
        "events": [
            {
                "id": r["id"],
                "action": r["action"],
                "domain": r["domain"],
                "meta": r["meta"],
                "created_at": str(r["created_at"]) if r["created_at"] else None,
            }
            for r in rows
        ],
    }
