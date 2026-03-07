from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any
from openai import OpenAI
import os
import json

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _safe_json(txt: str):
    try:
        return json.loads(txt)
    except Exception:
        return {}


def build_user_insight(db: Session, user_id: int) -> Dict[str, Any]:

    rows = db.execute(
        text("""
        SELECT message, response
        FROM memory
        WHERE user_id = :uid
        ORDER BY created_at DESC
        LIMIT 12
        """),
        {"uid": user_id},
    ).mappings().all()

    if not rows:
        return {}

    joined = "\n".join(
        f"Kullanıcı: {r['message']}\nSanrı: {r['response']}" for r in rows
    )

    prompt = f"""
Aşağıdaki konuşma geçmişine göre kullanıcı için kısa bir bilinç profili çıkar.

Sadece JSON dön.

Şema:

{{
"theme": "kullanıcının ana yaşam teması",
"focus": "şu anki odak alanı",
"symbol": "tekrar eden sembol",
"ritual_direction": "önerilen ritüel yönü",
"next_area": "uygulamada önerilen sonraki alan"
}}

Konuşma geçmişi:
{joined}
"""

    try:
        res = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Sadece geçerli JSON üret."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=300,
        )

        raw = res.choices[0].message.content or ""
        obj = _safe_json(raw)

    except Exception:
        obj = {}

    return {
        "theme": str(obj.get("theme", "")).strip(),
        "focus": str(obj.get("focus", "")).strip(),
        "symbol": str(obj.get("symbol", "")).strip(),
        "ritual_direction": str(obj.get("ritual_direction", "")).strip(),
        "next_area": str(obj.get("next_area", "")).strip(),
        "raw_json": raw.strip() if 'raw' in locals() else "",
    }


def save_user_insight(db: Session, user_id: int, insight: Dict[str, Any]):

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
            **insight
        },
    )

    db.commit()