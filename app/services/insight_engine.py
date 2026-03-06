# app/services/insight_engine.py

import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text
from openai import OpenAI
import os

from app.services.memory import get_user_memory


def _client():
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    return OpenAI(api_key=key, timeout=60)


def _model():
    return (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()


def _safe_json(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    return {
        "theme": "",
        "focus": "",
        "symbol": "",
        "ritual_direction": "",
        "next_area": "",
        "raw_json": raw,
    }


def build_user_insight(db: Session, user_id: int) -> Dict[str, Any]:
    history: List[Dict[str, str]] = get_user_memory(db, user_id=user_id, limit=20)

    if not history:
        return {
            "theme": "",
            "focus": "",
            "symbol": "",
            "ritual_direction": "",
            "next_area": "",
            "raw_json": "",
        }

    joined = "\n\n".join(
        [
            f"Kullanıcı: {h.get('message','')}\nSanrı: {h.get('response','')}"
            for h in history
        ]
    ).strip()

    client = _client()
    if client is None:
        return {
            "theme": "",
            "focus": "",
            "symbol": "",
            "ritual_direction": "",
            "next_area": "",
            "raw_json": "",
        }

    prompt = f"""
Aşağıdaki konuşma geçmişine göre kullanıcı için kısa bir bilinç profili çıkar.

Sadece JSON dön.
Şema:
{{
  "theme": "kullanıcının ana yaşam teması",
  "focus": "şu anki odak alanı",
  "symbol": "tekrar eden sembol veya ana imge",
  "ritual_direction": "önerilen ritüel yönü",
  "next_area": "uygulamada önerilen sonraki alan"
}}

Konuşma geçmişi:
{joined}
"""

    try:
        res = client.chat.completions.create(
            model=_model(),
            messages=[
                {"role": "system", "content": "Sadece geçerli JSON üret."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=300,
        )

        raw = res.choices[0].message.content or ""
        obj = _safe_json(raw)

        return {
            "theme": str(obj.get("theme") or "").strip(),
            "focus": str(obj.get("focus") or "").strip(),
            "symbol": str(obj.get("symbol") or "").strip(),
            "ritual_direction": str(obj.get("ritual_direction") or "").strip(),
            "next_area": str(obj.get("next_area") or "").strip(),
            "raw_json": raw.strip(),
        }
    except Exception:
        return {
            "theme": "",
            "focus": "",
            "symbol": "",
            "ritual_direction": "",
            "next_area": "",
            "raw_json": "",
        }


def save_user_insight(db: Session, user_id: int, insight: Dict[str, Any]) -> None:
    db.execute(
        text("""
            INSERT INTO user_insights
            (user_id, theme, focus, symbol, ritual_direction, next_area, raw_json, updated_at)
            VALUES
            (:user_id, :theme, :focus, :symbol, :ritual_direction, :next_area, :raw_json, now())
            ON CONFLICT (user_id)
            DO UPDATE SET
                theme = EXCLUDED.theme,
                focus = EXCLUDED.focus,
                symbol = EXCLUDED.symbol,
                ritual_direction = EXCLUDED.ritual_direction,
                next_area = EXCLUDED.next_area,
                raw_json = EXCLUDED.raw_json,
                updated_at = now()
        """),
        {
            "user_id": user_id,
            "theme": insight.get("theme", ""),
            "focus": insight.get("focus", ""),
            "symbol": insight.get("symbol", ""),
            "ritual_direction": insight.get("ritual_direction", ""),
            "next_area": insight.get("next_area", ""),
            "raw_json": insight.get("raw_json", ""),
        },
    )
    db.commit()


def get_user_insight(db: Session, user_id: int) -> Dict[str, Any]:
    row = db.execute(
        text("""
            SELECT theme, focus, symbol, ritual_direction, next_area, raw_json, updated_at
            FROM user_insights
            WHERE user_id = :user_id
            LIMIT 1
        """),
        {"user_id": user_id},
    ).mappings().first()

    if not row:
        return {
            "theme": "",
            "focus": "",
            "symbol": "",
            "ritual_direction": "",
            "next_area": "",
            "raw_json": "",
        }

    return {
        "theme": row.get("theme") or "",
        "focus": row.get("focus") or "",
        "symbol": row.get("symbol") or "",
        "ritual_direction": row.get("ritual_direction") or "",
        "next_area": row.get("next_area") or "",
        "raw_json": row.get("raw_json") or "",
        "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else "",
    }