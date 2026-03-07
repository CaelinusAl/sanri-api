import json
import os
from typing import Any, Dict, List

from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.orm import Session


def _client() -> OpenAI:
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _safe_json(raw: str) -> Dict[str, Any]:
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {
        "identity_summary": "",
        "recurring_symbols": "",
        "emotional_pattern": "",
        "current_focus": "",
        "suggested_next_step": "",
    }


def _get_recent_memory(db: Session, user_id: int, limit: int = 30) -> List[str]:
    rows = db.execute(
        text("""
            SELECT input_text, output_text
            FROM memory
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"user_id": user_id, "limit": limit},
    ).mappings().all()

    lines: List[str] = []
    for r in reversed(rows):
        inp = (r.get("input_text") or "").strip()
        out = (r.get("output_text") or "").strip()
        if inp:
            lines.append(f"Kullanıcı: {inp}")
        if out:
            lines.append(f"Sanrı: {out}")
    return lines


def build_memory_state(db: Session, user_id: int) -> Dict[str, Any]:
    joined = "\n".join(_get_recent_memory(db, user_id, limit=30)).strip()

    if not joined:
        return {
            "identity_summary": "",
            "recurring_symbols": "",
            "emotional_pattern": "",
            "current_focus": "",
            "suggested_next_step": "",
            "raw_json": "",
        }

    prompt = f"""
Aşağıdaki konuşma geçmişine göre kullanıcı için yaşayan hafıza özeti çıkar.

Sadece JSON dön.
Şema:
{{
  "identity_summary": "kullanıcının kısa öz kimlik özeti",
  "recurring_symbols": "tekrar eden semboller, imgeler veya temalar",
  "emotional_pattern": "duygusal akışın kısa özeti",
  "current_focus": "şu anki ana odak",
  "suggested_next_step": "önerilen bir sonraki küçük adım"
}}

Konuşma geçmişi:
{joined}
""".strip()

    res = _client().chat.completions.create(
        model=_model(),
        messages=[
            {"role": "system", "content": "Sadece geçerli JSON üret."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=350,
    )

    raw = (res.choices[0].message.content or "").strip()
    obj = _safe_json(raw)

    final = {
        "identity_summary": str(obj.get("identity_summary") or "").strip(),
        "recurring_symbols": str(obj.get("recurring_symbols") or "").strip(),
        "emotional_pattern": str(obj.get("emotional_pattern") or "").strip(),
        "current_focus": str(obj.get("current_focus") or "").strip(),
        "suggested_next_step": str(obj.get("suggested_next_step") or "").strip(),
        "raw_json": raw,
    }

    existing = db.execute(
        text("SELECT id FROM user_memory_state WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).mappings().first()

    if existing:
        db.execute(
            text("""
                UPDATE user_memory_state
                SET
                  identity_summary = :identity_summary,
                  recurring_symbols = :recurring_symbols,
                  emotional_pattern = :emotional_pattern,
                  current_focus = :current_focus,
                  suggested_next_step = :suggested_next_step,
                  raw_json = :raw_json,
                  updated_at = now()
                WHERE user_id = :user_id
            """),
            {"user_id": user_id, **final},
        )
    else:
        db.execute(
            text("""
                INSERT INTO user_memory_state
                (user_id, identity_summary, recurring_symbols, emotional_pattern, current_focus, suggested_next_step, raw_json)
                VALUES
                (:user_id, :identity_summary, :recurring_symbols, :emotional_pattern, :current_focus, :suggested_next_step, :raw_json)
            """),
            {"user_id": user_id, **final},
        )

    db.commit()
    return final


def get_memory_state(db: Session, user_id: int) -> Dict[str, Any]:
    row = db.execute(
        text("""
            SELECT identity_summary, recurring_symbols, emotional_pattern, current_focus, suggested_next_step, raw_json
            FROM user_memory_state
            WHERE user_id = :user_id
            LIMIT 1
        """),
        {"user_id": user_id},
    ).mappings().first()

    if not row:
        return {
            "identity_summary": "",
            "recurring_symbols": "",
            "emotional_pattern": "",
            "current_focus": "",
            "suggested_next_step": "",
            "raw_json": "",
        }

    return dict(row)