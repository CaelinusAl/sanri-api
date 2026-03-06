# app/services/system_feed.py

import os
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from openai import OpenAI


# ----------------------------------------------------
# helpers
# ----------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _openai_client() -> Optional[OpenAI]:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
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


# ----------------------------------------------------
# GET LATEST FEED
# ----------------------------------------------------

def get_latest_feed(db: Session, lang: str = "tr") -> Dict[str, Any]:

    row = db.execute(
        text(
            """
            SELECT id, created_at, kind, title, subtitle,
                   body_tr, body_en, source_url, tags
            FROM system_feed_items
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        )
    ).mappings().first()

    if not row:
        return _stub_feed(lang)

    return {
        "id": row.get("id"),
        "created_at": (
            row.get("created_at").isoformat()
            if row.get("created_at")
            else None
        ),
        "kind": row.get("kind") or "system",
        "title": row.get("title") or "",
        "subtitle": row.get("subtitle") or "",
        "body_tr": row.get("body_tr") or "",
        "body_en": row.get("body_en") or "",
        "source_url": row.get("source_url") or "",
        "tags": row.get("tags") or "",
    }


# ----------------------------------------------------
# GENERATE + STORE
# ----------------------------------------------------

def generate_and_store_feed(db: Session, lang: str = "tr") -> Dict[str, Any]:

    item = _generate_item(lang)

    created_at = _now_utc()

    db.execute(
        text(
            """
            INSERT INTO system_feed_items
            (created_at, kind, title, subtitle,
             body_tr, body_en, source_url, tags)
            VALUES
            (:created_at, :kind, :title, :subtitle,
             :body_tr, :body_en, :source_url, :tags)
            """
        ),
        {
            "created_at": created_at,
            "kind": item.get("kind"),
            "title": item.get("title"),
            "subtitle": item.get("subtitle"),
            "body_tr": item.get("body_tr"),
            "body_en": item.get("body_en"),
            "source_url": item.get("source_url"),
            "tags": item.get("tags"),
        },
    )

    db.commit()

    return get_latest_feed(db, lang)


# ----------------------------------------------------
# GENERATE ITEM
# ----------------------------------------------------

def _generate_item(lang: str = "tr") -> Dict[str, Any]:

    client = _openai_client()

    if client is None:
        return _stub_feed(lang)

    system = (
        "You generate a daily consciousness stream for an AI system feed. "
        "Return JSON only."
    )

    user = {
        "task": "Generate today's System Feed",
        "schema": {
            "kind": "system",
            "title": "short title",
            "subtitle": "short subtitle",
            "body_tr": "Turkish text",
            "body_en": "English text",
            "source_url": "",
            "tags": "comma separated"
        }
    }

    try:

        resp = client.chat.completions.create(
            model=_model_name(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
            temperature=0.6,
            max_tokens=500,
        )

        raw = (resp.choices[0].message.content or "").strip()

        obj = _safe_json(raw)

        out = {
            "kind": "system",
            "title": str(obj.get("title") or "").strip(),
            "subtitle": str(obj.get("subtitle") or "").strip(),
            "body_tr": str(obj.get("body_tr") or "").strip(),
            "body_en": str(obj.get("body_en") or "").strip(),
            "source_url": str(obj.get("source_url") or "").strip(),
            "tags": str(obj.get("tags") or "").strip(),
        }

        if not out["title"]:
            return _stub_feed(lang)

        return out

    except Exception:
        return _stub_feed(lang)


# ----------------------------------------------------
# STUB
# ----------------------------------------------------

def _stub_feed(lang: str = "tr") -> Dict[str, Any]:

    return {
        "kind": "system",
        "title": "Signal" if lang == "en" else "Sinyal",
        "subtitle": (
            "System is opening a new layer."
            if lang == "en"
            else "Sistem yeni bir katman açıyor."
        ),
        "body_tr":
            "Bugün sistem senden tek şey istiyor: netlik.\n"
            "Bir cümle yaz.\n"
            "Bir karar seç.\n"
            "Sonra bir adım at.",
        "body_en":
            "Today the system asks for clarity.\n"
            "Write one sentence.\n"
            "Choose one decision.\n"
            "Take one step.",
        "source_url": "",
        "tags": "system,signal",
    }