# app/routes/system_feed.py

from fastapi import APIRouter, Depends, Query, HTTPException
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
    try:
        lang = normalize_lang(lang)
        return get_latest_feed(db, lang)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SYSTEM_FEED_READ_FAILED",
                "error": str(e)
            }
        )


# ----------------------------------------------------
# GENERATE (GET for browser test)
# ----------------------------------------------------

@router.get("/system-feed/generate")
def system_feed_generate_get(
    lang: str = Query(default="tr"),
    db: Session = Depends(get_db)
):
    try:
        lang = normalize_lang(lang)
        item = generate_and_store_feed(db, lang)

        return {
            "status": "generated",
            "item": item
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SYSTEM_FEED_GENERATE_FAILED",
                "error": str(e)
            }
        )

# ----------------------------------------------------
# GENERATE (POST for internal automation)
# ----------------------------------------------------

@router.post("/system-feed/generate")
def system_feed_generate_post(
    lang: str = Query(default="tr"),
    db: Session = Depends(get_db)
):
    try:
        lang = normalize_lang(lang)
        item = generate_and_store_feed(db, lang)

        return {
            "status": "generated",
            "item": item
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SYSTEM_FEED_GENERATE_FAILED",
                "error": str(e)
            }
        )


# ----------------------------------------------------
# DB CHECK (DEBUG)
# ----------------------------------------------------

@router.get("/system-feed/db-check")
def system_feed_db_check(
    db: Session = Depends(get_db)
):
    row = db.execute(
        text("SELECT current_database() AS db, current_user AS usr, now() AS now")
    ).mappings().first()

    return {
        "database": row.get("db"),
        "user": row.get("usr"),
        "now": str(row.get("now")),
    }


