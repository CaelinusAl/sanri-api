import os
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text
from openai import OpenAI


def _client():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    return OpenAI(api_key=key)


def latest_ritual(db: Session):

    row = db.execute(text("""
        SELECT id, created_at, title, intention,
               body_tr, body_en, duration, tags
        FROM ritual_feed_items
        ORDER BY created_at DESC
        LIMIT 1
    """)).mappings().first()

    if not row:
        return {
            "title": "Nefes Ritüeli",
            "intention": "Zihni temizlemek",
            "body_tr": "3 dakika nefes al ve ver.",
            "body_en": "Breathe slowly for 3 minutes.",
            "duration": "3 min",
            "tags": "ritual,breath"
        }

    return dict(row)


def generate_ritual(db: Session):

    client = _client()

    if client is None:
        return latest_ritual(db)

    prompt = """
Create a daily consciousness ritual.

Structure JSON:

title
intention
body_tr
body_en
duration
tags
"""

    try:

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"You create short spiritual rituals."},
                {"role":"user","content":prompt}
            ],
            temperature=0.6
        )

        obj = json.loads(res.choices[0].message.content)

    except Exception:
        return latest_ritual(db)

    db.execute(text("""
        INSERT INTO ritual_feed_items
        (title,intention,body_tr,body_en,duration,tags)
        VALUES
        (:title,:intention,:body_tr,:body_en,:duration,:tags)
    """), obj)

    db.commit()

    return latest_ritual(db)