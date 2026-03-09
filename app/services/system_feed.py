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
# GET LATEST FEED
# ----------------------------------------------------

def get_latest_feed(db: Optional[Session], lang: str = "tr") -> Dict[str, Any]:
    lang = _normalize_lang(lang)

    if db is None:
        out = _stub_feed(lang)
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
        out = _stub_feed(lang)
        out["warning"] = "DB_READ_FAILED"
        return out
    except Exception:
        out = _stub_feed(lang)
        out["warning"] = "DB_READ_UNKNOWN_ERROR"
        return out

    if not row:
        out = _stub_feed(lang)
        out["warning"] = "NO_ROWS"
        return out

    tags = row.get("tags")
    if isinstance(tags, list):
        tags = ",".join(str(x) for x in tags if x is not None)
    elif tags is None:
        tags = ""
    else:
        tags = str(tags)

    created_at = row.get("created_at")
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()
    elif created_at is None:
        created_at = None
    else:
        created_at = str(created_at)

    return {
        "id": row.get("id"),
        "created_at": created_at,
        "kind": row.get("kind") or "system",
        "title": row.get("title") or "",
        "subtitle": row.get("subtitle") or "",
        "body_tr": row.get("body_tr") or "",
        "body_en": row.get("body_en") or "",
        "source_url": row.get("source_url") or "",
        "tags": tags,
    }


# ----------------------------------------------------
# GENERATE + STORE
# ----------------------------------------------------

def generate_and_store_feed(db: Optional[Session], lang: str = "tr") -> Dict[str, Any]:
    lang = _normalize_lang(lang)
    item = _generate_item(lang)

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
                    id,
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
                    DEFAULT,
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
        out = _stub_feed(lang)
        out["warning"] = "OPENAI_KEY_MISSING"
        return out

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

        if lang == "tr" and not out["body_tr"]:
            out["body_tr"] = out["body_en"] or _stub_feed("tr")["body_tr"]

        if lang == "en" and not out["body_en"]:
            out["body_en"] = out["body_tr"] or _stub_feed("en")["body_en"]

        return out

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