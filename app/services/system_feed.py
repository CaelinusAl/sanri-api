# app/services/system_feed.py
import time
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text


def _safe_lang(lang: Optional[str]) -> str:
    v = (lang or "tr").strip().lower()
    return v if v in ("tr", "en") else "tr"


def get_latest_feed(db: Session, lang: str = "tr") -> Dict[str, Any]:
    """
    DB'den en son system_feed_items kaydını döndürür.
    UI için normalize edilmiş bir obje verir.
    """
    lang = _safe_lang(lang)

    row = db.execute(
        text(
            """
            SELECT id, created_at, kind, title, subtitle, body_tr, body_en, source_url, tags
            FROM system_feed_items
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
    ).fetchone()

    if not row:
        # veri yoksa "boş ama anlamlı" fallback
        return {
            "items": [],
            "latest": {
                "signal": "Sistem sessiz." if lang == "tr" else "System is quiet.",
                "symbol": "Henüz veri yok." if lang == "tr" else "No data yet.",
                "message": "Yeni bir akış üretilecek." if lang == "tr" else "A new stream will be generated.",
                "action": "Bekle" if lang == "tr" else "Wait",
                "share": "",
            },
        }

    message = (row.body_tr or "") if lang == "tr" else (row.body_en or row.body_tr or "")

    latest = {
        "id": row.id,
        "created_at": str(row.created_at),
        "kind": row.kind or "system",
        "signal": row.title or "",
        "symbol": row.subtitle or "",
        "message": message,
        "action": "Observe",
        "share": "",
        "source_url": row.source_url or "",
        "tags": row.tags or "",
    }

    return {"items": [latest], "latest": latest}


def generate_daily_stub(db: Session, lang: str = "tr") -> Dict[str, Any]:
    """
    DB'ye 1 adet system feed kaydı ekler.
    Not: id otomatik artmıyorsa bile çalışsın diye MAX(id)+1 kullanır.
    """
    lang = _safe_lang(lang)

    try:
        next_id = db.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM system_feed_items")).scalar()
        next_id = int(next_id or 1)

        body_tr = (
            "Bugün sistem yeni bir bilinç katmanı açtı.\n"
            "Kaos sandığın şey, düzenin görünmeyen hâli.\n"
            "Tek adım: nefes al, ver, sadece gözlemle."
        )
        body_en = (
            "Today the system opened a new layer of consciousness.\n"
            "What looks like chaos is hidden order.\n"
            "One step: inhale, exhale, simply observe."
        )

        title = "Yeni bilinç akışı başladı" if lang == "tr" else "A new stream started"
        subtitle = "Sistem" if lang == "tr" else "System"

        db.execute(
            text(
                """
                INSERT INTO system_feed_items
                (id, created_at, kind, title, subtitle, body_tr, body_en, source_url, tags)
                VALUES
                (:id, NOW(), :kind, :title, :subtitle, :body_tr, :body_en, :source_url, :tags)
                """
            ),
            {
                "id": next_id,
                "kind": "system",
                "title": title,
                "subtitle": subtitle,
                "body_tr": body_tr,
                "body_en": body_en,
                "source_url": "",
                "tags": "system,signal",
            },
        )

        db.commit()

        return {
            "status": "generated",
            "id": next_id,
            "lang": lang,
            "title": title,
            "subtitle": subtitle,
        }

    except Exception as e:
        db.rollback()
        return {"status": "error", "error": str(e)}