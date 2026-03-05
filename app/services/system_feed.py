# app/services/system_feed.py
import os
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from openai import OpenAI


# ---------- helpers ----------
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _openai_client() -> Optional[OpenAI]:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    # OpenAI python 1.x ile uyumlu
    return OpenAI(api_key=key, timeout=60)


def _model_name() -> str:
    return (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()


def _safe_json(x: Any) -> Dict[str, Any]:
    if isinstance(x, dict):
        return x
    try:
        return json.loads(str(x))
    except Exception:
        return {"raw": str(x)}


# ---------- DB schema contract ----------
# Table: system_feed_items
# Columns: id (bigserial), created_at (timestamptz), kind, title, subtitle, body_tr, body_en, source_url, tags


def get_latest_feed(db: Session, lang: str = "tr") -> Dict[str, Any]:
    # En son kaydı çek
    row = db.execute(
        text(
            """
            SELECT id, created_at, kind, title, subtitle, body_tr, body_en, source_url, tags
            FROM system_feed_items
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        )
    ).mappings().first()

    if not row:
        # hiç kayıt yoksa stub dön
        return _stub_feed(lang=lang)

    # normalize
    return {
        "id": row.get("id"),
        "created_at": (row.get("created_at").isoformat() if row.get("created_at") else None),
        "kind": row.get("kind") or "system",
        "title": row.get("title") or "",
        "subtitle": row.get("subtitle") or "",
        "body_tr": row.get("body_tr") or "",
        "body_en": row.get("body_en") or "",
        "source_url": row.get("source_url") or "",
        "tags": row.get("tags") or "",
    }


def generate_and_store_feed(db: Session, lang: str = "tr") -> Dict[str, Any]:
    """
    1) LLM ile üret (yoksa stub)
    2) DB’ye insert
    3) insert edilen kaydı geri döndür
    """
    item = _generate_item(lang=lang)

    # DB insert (created_at default now() ama biz de set ediyoruz)
    created_at = _now_utc()

    db.execute(
        text(
            """
            INSERT INTO system_feed_items (created_at, kind, title, subtitle, body_tr, body_en, source_url, tags)
            VALUES (:created_at, :kind, :title, :subtitle, :body_tr, :body_en, :source_url, :tags)
            """
        ),
        {
            "created_at": created_at,
            "kind": item.get("kind") or "system",
            "title": item.get("title") or "",
            "subtitle": item.get("subtitle") or "",
            "body_tr": item.get("body_tr") or "",
            "body_en": item.get("body_en") or "",
            "source_url": item.get("source_url") or "",
            "tags": item.get("tags") or "",
        },
    )
    db.commit()

    # En son kaydı dön
    return get_latest_feed(db, lang)


def _generate_item(lang: str = "tr") -> Dict[str, Any]:
    """
    LLM yoksa ya da hata olursa stub döner.
    """
    client = _openai_client()
    if client is None:
        return _stub_feed(lang=lang)

    model = _model_name()

    system = (
        "You are Sanri System Feed generator. "
        "Return STRICT JSON only. No markdown. No code fences."
    )

    # her iki dili birlikte üret, mobil tarafı kolaylaşır
    user = {
        "task": "Generate today's System Feed item.",
        "schema": {
            "kind": "system",
            "title": "short title",
            "subtitle": "short subtitle",
            "body_tr": "Turkish body (multi-line allowed)",
            "body_en": "English body (multi-line allowed)",
            "source_url": "optional",
            "tags": "comma-separated tags"
        },
        "style": "matrix, consciousness, minimal, actionable, warm",
        "constraints": [
            "JSON object only",
            "title/subtitle max 80 chars",
            "body_tr/body_en max 900 chars",
        ],
    }

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.6,
            max_tokens=500,
        )

        raw = (resp.choices[0].message.content or "").strip()
        obj = _safe_json(raw)

        # minimum alanlar
        out = {
            "kind": "system",
            "title": str(obj.get("title") or "").strip(),
            "subtitle": str(obj.get("subtitle") or "").strip(),
            "body_tr": str(obj.get("body_tr") or "").strip(),
            "body_en": str(obj.get("body_en") or "").strip(),
            "source_url": str(obj.get("source_url") or "").strip(),
            "tags": str(obj.get("tags") or "").strip(),
        }

        # boş geldiyse stub’a düş
        if not out["title"] and not out["body_tr"] and not out["body_en"]:
            return _stub_feed(lang=lang)

        # lang TR ise TR alanı boş kalmasın
        if lang == "tr" and not out["body_tr"]:
            out["body_tr"] = out["body_en"] or "Sistem akışı hazırlanıyor."
        if lang == "en" and not out["body_en"]:
            out["body_en"] = out["body_tr"] or "System stream is preparing."

        return out

    except Exception:
        # hiçbir şekilde 500 verme — stub
        return _stub_feed(lang=lang)


def _stub_feed(lang: str = "tr") -> Dict[str, Any]:
    # DB’ye de yazılabilir, ama burada sadece return obj
    return {
        "kind": "system",
        "title": "Signal" if lang == "en" else "Sinyal",
        "subtitle": "System is opening a new layer." if lang == "en" else "Sistem yeni bir katman açıyor.",
        "body_tr": (
            "Bugün sistem senden tek şey istiyor: **netlik**.\n"
            "Bir cümle yaz. Bir karar seç. Sonra 1 adım at.\n"
            "Kaos sandığın şey, sıraya girmek üzere olan veridir."
        ),
        "body_en": (
            "Today the system asks for one thing: **clarity**.\n"
            "Write one sentence. Choose one decision. Then take 1 step.\n"
            "What you call chaos is data about to align."
        ),
        "source_url": "",
        "tags": "system,signal,clarity",
    }