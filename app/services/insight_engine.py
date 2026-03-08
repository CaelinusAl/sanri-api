from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any
from openai import OpenAI

import os
import json


# ---------------------------------------------------
# OPENAI CLIENT
# ---------------------------------------------------

def get_openai_client():
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()

    if not api_key:
        return None

    return OpenAI(api_key=api_key)


MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


# ---------------------------------------------------
# SAFE JSON
# ---------------------------------------------------

def _safe_json(txt: str):
    try:
        return json.loads(txt)
    except Exception:
        return {}


# ---------------------------------------------------
# BUILD USER INSIGHT
# ---------------------------------------------------

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
        f"Kullanıcı: {r['message']}\nSanrı: {r['response']}"
        for r in rows
    )

    prompt = f"""
Aşağıdaki konuşma geçmişine göre kullanıcı için kısa bir bilinç profili çıkar.

Sadece JSON dön.

{{
 "mood": "...",
 "theme": "...",
 "state": "...",
 "insight": "..."
}}

Konuşma:
{joined}
"""

    client = get_openai_client()

    if client is None:
        return {}

    try:

        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You generate user insight."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=200,
        )

        txt = resp.choices[0].message.content or ""

        return _safe_json(txt)

    except Exception:
        return {}