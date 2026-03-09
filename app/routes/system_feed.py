from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.services.system_feed import get_latest_feed, generate_and_store_feed

router = APIRouter(prefix="/content", tags=["content"])


# ----------------------------------------------------
# helper
# ----------------------------------------------------

def normalize_lang(lang: str) -> str:
    lang = (lang or "tr").lower().strip()
    if lang not in ("tr", "en"):
        lang = "tr"
    return lang


# ----------------------------------------------------
# GET latest system feed
# ----------------------------------------------------

@router.get("/system-feed")
def system_feed(
    lang: str = Query(default="tr"),
    db: Session = Depends(get_db)
):
    lang = normalize_lang(lang)

    try:
        item = get_latest_feed(db, lang)
        return {
            "status": "ok",
            "item": item
        }
    except Exception as e:
        # cron / mobile / web hiçbir zaman düz 500 yerine anlamlı çıktı alsın
        return {
            "status": "fallback",
            "item": {
                "kind": "system",
                "title": "Sinyal",
                "subtitle": "Sistem yeni bir katman açıyor.",
                "body_tr": (
                    "Bugün sistem senden tek şey istiyor: netlik.\n"
                    "Bir cümle yaz.\n"
                    "Bir karar seç.\n"
                    "Sonra bir adım at."
                ),
                "body_en": (
                    "Today the system asks for clarity.\n"
                    "Write one sentence.\n"
                    "Choose one decision.\n"
                    "Take one step."
                ),
                "source_url": "",
                "tags": "system,signal",
                "warning": "SYSTEM_FEED_READ_FAILED",
            },
            "error": str(e),
        }


# ----------------------------------------------------
# GENERATE (GET for browser test / cron)
# ----------------------------------------------------

@router.get("/system-feed/generate")
def system_feed_generate_get(
    lang: str = Query(default="tr"),
    db: Session = Depends(get_db)
):
    lang = normalize_lang(lang)

    try:
        item = generate_and_store_feed(db, lang)
        return {
            "status": "generated",
            "item": item
        }
    except Exception as e:
        # cronjob kırılmasın, fallback dönsün
        return {
            "status": "fallback-generated",
            "item": {
                "kind": "system",
                "title": "Sinyal",
                "subtitle": "Sistem yeni bir katman açıyor.",
                "body_tr": (
                    "Bugün sistem senden tek şey istiyor: netlik.\n"
                    "Bir cümle yaz.\n"
                    "Bir karar seç.\n"
                    "Sonra bir adım at."
                ),
                "body_en": (
                    "Today the system asks for clarity.\n"
                    "Write one sentence.\n"
                    "Choose one decision.\n"
                    "Take one step."
                ),
                "source_url": "",
                "tags": "system,signal",
                "warning": "SYSTEM_FEED_GENERATE_FAILED",
            },
            "error": str(e),
        }


# ----------------------------------------------------
# GENERATE (POST for internal automation)
# ----------------------------------------------------

@router.post("/system-feed/generate")
def system_feed_generate_post(
    lang: str = Query(default="tr"),
    db: Session = Depends(get_db)
):
    lang = normalize_lang(lang)

    try:
        item = generate_and_store_feed(db, lang)
        return {
            "status": "generated",
            "item": item
        }
    except Exception as e:
        return {
            "status": "fallback-generated",
            "item": {
                "kind": "system",
                "title": "Sinyal",
                "subtitle": "Sistem yeni bir katman açıyor.",
                "body_tr": (
                    "Bugün sistem senden tek şey istiyor: netlik.\n"
                    "Bir cümle yaz.\n"
                    "Bir karar seç.\n"
                    "Sonra bir adım at."
                ),
                "body_en": (
                    "Today the system asks for clarity.\n"
                    "Write one sentence.\n"
                    "Choose one decision.\n"
                    "Take one step."
                ),
                "source_url": "",
                "tags": "system,signal",
                "warning": "SYSTEM_FEED_GENERATE_FAILED",
            },
            "error": str(e),
        }


# ----------------------------------------------------
# DB CHECK (DEBUG)
# ----------------------------------------------------

@router.get("/system-feed/db-check")
def system_feed_db_check(
    db: Session = Depends(get_db)
):
    try:
        row = db.execute(
            text("SELECT current_database() AS db, current_user AS usr, now() AS now")
        ).mappings().first()

        return {
            "status": "ok",
            "database": row.get("db") if row else None,
            "user": row.get("usr") if row else None,
            "now": str(row.get("now")) if row else None,
        }
    except Exception as e:
        return {
            "status": "db-check-failed",
            "database": None,
            "user": None,
            "now": None,
            "error": str(e),
        }