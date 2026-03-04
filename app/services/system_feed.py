# app/services/system_feed.py
import os
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

# Eğer DB modelin varsa kullan; yoksa sistem yine çalışsın diye try/except
try:
    from app.models.system_feed import SystemFeed # type: ignore
except Exception:
    SystemFeed = None # type: ignore


def _today_key() -> str:
    # YYYY-MM-DD
    return time.strftime("%Y-%m-%d")


def generate_daily_stub(lang: str = "tr") -> Dict[str, Any]:
    """DB yoksa ya da model yoksa bile app çökmesin: demo içerik döndür."""
    lang = (lang or "tr").lower()
    if lang not in ("tr", "en"):
        lang = "tr"

    if lang == "tr":
        return {
            "date": _today_key(),
            "title": "SYSTEM FEED",
            "kicker": "GÜNLÜK AKIŞ",
            "items": [
                {
                    "id": "signal",
                    "title": "Sinyal",
                    "text": "Bugün sistem senden hız değil, netlik istiyor.",
                },
                {
                    "id": "pattern",
                    "title": "Örüntü",
                    "text": "Tekrarlayan döngüyü izle: hangi cümle seni aşağı çekiyor?",
                },
                {
                    "id": "action",
                    "title": "Tek Adım",
                    "text": "1 küçük karar ver ve uygula. Büyük akış böyle açılır.",
                },
            ],
        }

    return {
        "date": _today_key(),
        "title": "SYSTEM FEED",
        "kicker": "DAILY STREAM",
        "items": [
            {
                "id": "signal",
                "title": "Signal",
                "text": "Today the system asks for clarity, not speed.",
            },
            {
                "id": "pattern",
                "title": "Pattern",
                "text": "Watch the repeating loop: which sentence pulls you down?",
            },
            {
                "id": "action",
                "title": "One Step",
                "text": "Make one small decision and do it. The stream opens like this.",
            },
        ],
    }


def get_latest_feed(db: Session, lang: str = "tr") -> Dict[str, Any]:
    """
    1) SystemFeed modeli varsa DB’den bugün kaydı getir / yoksa stub döndür.
    2) Model yoksa direkt stub.
    """
    lang = (lang or "tr").lower()
    if lang not in ("tr", "en"):
        lang = "tr"

    if SystemFeed is None:
        return generate_daily_stub(lang)

    today = _today_key()
    try:
        row = (
            db.query(SystemFeed)
            .filter(SystemFeed.date == today)
            .filter(SystemFeed.lang == lang)
            .order_by(SystemFeed.created_at.desc())
            .first()
        )
    except Exception:
        row = None

    if not row:
        # otomatik create (minimum)
        payload = generate_daily_stub(lang)
        try:
            row = SystemFeed(
                date=today,
                lang=lang,
                payload=payload,
            )
            db.add(row)
            db.commit()
        except Exception:
            db.rollback()
            return payload

    # row.payload dict olmalı
    try:
        return row.payload if isinstance(row.payload, dict) else generate_daily_stub(lang)
    except Exception:
        return generate_daily_stub(lang)