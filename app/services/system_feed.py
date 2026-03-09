import os
import json
from typing import Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from openai import OpenAI


# ----------------------------------------------------
# helpers
# ----------------------------------------------------

def _normalize_lang(lang: str) -> str:
    lang = (lang or "tr").strip().lower()
    if lang not in ("tr", "en"):
        return "tr"
    return lang


def _openai_client() -> Optional[OpenAI]:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    return OpenAI(api_key=key, timeout=60)


def _model_name() -> str:
    return (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()


def _strip_code_fences(raw: str) -> str:
    raw = (raw or "").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return raw


def _safe_json(x: Any) -> Dict[str, Any]:
    if isinstance(x, dict):
        return x
    try:
        return json.loads(str(x))
    except Exception:
        return {"raw": str(x)}


# ----------------------------------------------------
# FINAL NORMALIZER
# ----------------------------------------------------

def _finalize_feed(item: Dict[str, Any], lang: str = "tr") -> Dict[str, Any]:
    lang = _normalize_lang(lang)

    title = str(item.get("title") or "").strip()
    subtitle = str(item.get("subtitle") or "").strip()
    body_tr = str(item.get("body_tr") or "").strip()
    body_en = str(item.get("body_en") or "").strip()
    source_url = str(item.get("source_url") or "").strip()
    tags = item.get("tags") or ""

    if isinstance(tags, list):
        tags = ",".join(str(x).strip() for x in tags if str(x).strip())
    else:
        tags = str(tags).strip()

    if not title:
        title = "Signal" if lang == "en" else "Sinyal"

    if not subtitle:
        subtitle = (
            "System is opening a new layer."
            if lang == "en"
            else "Sistem yeni bir katman açıyor."
        )

    if not body_tr:
        body_tr = (
            "Bugün sistem senden tek şey istiyor: netlik.\n"
            "Bir cümle yaz.\n"
            "Bir karar seç.\n"
            "Sonra bir adım at."
        )

    if not body_en:
        body_en = (
            "Today the system asks for clarity.\n"
            "Write one sentence.\n"
            "Choose one decision.\n"
            "Take one step."
        )

    if not tags:
        tags = "system,signal"

    return {
        "kind": str(item.get("kind") or "system").strip() or "system",
        "title": title,
        "subtitle": subtitle,
        "body_tr": body_tr,
        "body_en": body_en,
        "source_url": source_url,
        "tags": tags,
    }


# ----------------------------------------------------
# GET LATEST FEED
# ----------------------------------------------------

def get_latest_feed(db: Optional[Session], lang: str = "tr") -> Dict[str, Any]:
    lang = _normalize_lang(lang)

    if db is None:
        out = _finalize_feed(_stub_feed(lang), lang)
        out["warning"] = "DB_MISSING"
        return out

    try:
        row = db.execute(
            text(
                """
                SELECT
                    id,
                    created_at,
                    kind,
                    title,
                    subtitle,
                    body_tr,
                    body_en,
                    source_url,
                    tags
                FROM system_feed_items
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            )
        ).mappings().first()
    except SQLAlchemyError:
        out = _finalize_feed(_stub_feed(lang), lang)
        out["warning"] = "DB_READ_FAILED"
        return out
    except Exception:
        out = _finalize_feed(_stub_feed(lang), lang)
        out["warning"] = "DB_READ_UNKNOWN_ERROR"
        return out

    if not row:
        out = _finalize_feed(_stub_feed(lang), lang)
        out["warning"] = "NO_ROWS"
        return out

    created_at = row.get("created_at")
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()
    elif created_at is None:
        created_at = None
    else:
        created_at = str(created_at)

    out = _finalize_feed(dict(row), lang)
    out["id"] = row.get("id")
    out["created_at"] = created_at
    return out


# ----------------------------------------------------
# GENERATE + STORE
# ----------------------------------------------------

def generate_and_store_feed(db: Optional[Session], lang: str = "tr") -> Dict[str, Any]:
    lang = _normalize_lang(lang)
    item = _finalize_feed(_generate_item(lang), lang)

    if db is None:
        out = dict(item)
        out["warning"] = "DB_MISSING_NOT_STORED"
        return out

    try:
        db.execute(
            text(
                """
                INSERT INTO system_feed_items
                (
                    kind,
                    title,
                    subtitle,
                    body_tr,
                    body_en,
                    source_url,
                    tags
                )
                VALUES
                (
                    :kind,
                    :title,
                    :subtitle,
                    :body_tr,
                    :body_en,
                    :source_url,
                    :tags
                )
                """
            ),
            {
                "kind": item["kind"],
                "title": item["title"],
                "subtitle": item["subtitle"],
                "body_tr": item["body_tr"],
                "body_en": item["body_en"],
                "source_url": item["source_url"],
                "tags": item["tags"],
            },
        )
        db.commit()
    except SQLAlchemyError:
        try:
            db.rollback()
        except Exception:
            pass
        out = dict(item)
        out["warning"] = "DB_WRITE_FAILED_NOT_STORED"
        return out
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        out = dict(item)
        out["warning"] = "DB_WRITE_UNKNOWN_ERROR_NOT_STORED"
        return out

    return get_latest_feed(db, lang)


# ----------------------------------------------------
# GENERATE ITEM
# ----------------------------------------------------

def _generate_item(lang: str = "tr") -> Dict[str, Any]:
    lang = _normalize_lang(lang)

    client = _openai_client()
    if client is None:
        stub = _stub_feed(lang)
        stub["warning"] = "OPENAI_KEY_MISSING"
        return stub

    system = (
        "You generate a daily consciousness stream for an AI system feed. "
        "Return valid JSON only. No markdown. No code fences."
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
        },
        "style": [
            "minimal",
            "clear",
            "warm",
            "consciousness-oriented",
            "matrix-aware"
        ],
        "constraints": [
            "title max 80 chars",
            "subtitle max 120 chars",
            "body_tr/body_en max 900 chars"
        ]
    }

    try:
        resp = client.chat.completions.create(
            model=_model_name(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.6,
            max_tokens=500,
        )

        raw = (resp.choices[0].message.content or "").strip()
        raw = _strip_code_fences(raw)
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

        if not out["title"] or (not out["body_tr"] and not out["body_en"]):
            stub = _stub_feed(lang)
            stub["warning"] = "MODEL_OUTPUT_INVALID"
            return stub

        return _finalize_feed(out, lang)

    except Exception:
        stub = _stub_feed(lang)
        stub["warning"] = "OPENAI_GENERATION_FAILED"
        return stub


# ----------------------------------------------------
# STUB
# ----------------------------------------------------

def _stub_feed(lang: str = "tr") -> Dict[str, Any]:
    lang = _normalize_lang(lang)

    return {
        "kind": "system",
        "title": "Signal" if lang == "en" else "Sinyal",
        "subtitle": (
            "System is opening a new layer."
            if lang == "en"
            else "Sistem yeni bir katman açıyor."
        ),
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
    }