"""
Gunun Hissi -- aggregates recent yanki field data into a daily collective feeling.
Runs via scheduler or HTTP cron.
"""
import json
import logging
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.daily_feeling import DailyFeeling
from app.models.yanki import YankiPost, YankiFieldEcho

log = logging.getLogger("sanri.daily_feeling")

ALLOWED_HZ = [396, 417, 528, 639, 741, 852, 963]

HZ_LABEL = {
    396: "Kök",
    417: "Sakral",
    528: "Kalp merkezi",
    639: "Bağ & uyum",
    741: "Boğaz",
    852: "Alın",
    963: "Taç",
}

POETIC_FALLBACKS = [
    {"tr": "Bugün kolektif alan sessiz ama derin bir nefes alıyor.", "en": "The collective field is breathing deeply today.", "hz": 528},
    {"tr": "Bugün bağ kurma ihtiyacı yükseliyor — yalnız değilsin.", "en": "The need for connection is rising today — you're not alone.", "hz": 639},
    {"tr": "Bugün bir şeyler değişmek istiyor. Hissedebiliyor musun?", "en": "Something wants to change today. Can you feel it?", "hz": 417},
    {"tr": "Bugün içeride bir farkındalık büyüyor.", "en": "An awareness is growing inside today.", "hz": 852},
    {"tr": "Bugün herkes biraz daha hafif olmak istiyor.", "en": "Everyone wants to feel a little lighter today.", "hz": 528},
]


def _period():
    hour = datetime.utcnow().hour
    return "morning" if hour < 14 else "evening"


def _get_fallback():
    idx = date.today().toordinal() % len(POETIC_FALLBACKS)
    fb = POETIC_FALLBACKS[idx]
    return fb["hz"], fb["tr"], fb["en"], [], 0


def _aggregate_yanki(db: Session):
    """Query last 24h of yanki field posts and aggregate."""
    cutoff = datetime.utcnow() - timedelta(hours=24)

    posts = (
        db.query(YankiPost)
        .filter(
            YankiPost.post_source == "anlasilma_field",
            YankiPost.status == "published",
            YankiPost.created_at >= cutoff,
        )
        .all()
    )

    if not posts:
        return None

    hz_counter = Counter()
    tag_counter = Counter()
    for p in posts:
        if p.frequency_hz and p.frequency_hz in ALLOWED_HZ:
            hz_counter[p.frequency_hz] += 1
        if p.energy_feel:
            parts = p.energy_feel.split("·")
            for part in parts:
                tag = part.strip()
                if tag and len(tag) < 30:
                    tag_counter[tag] += 1

    top_hz = hz_counter.most_common(1)[0][0] if hz_counter else 528
    top_tags = [t for t, _ in tag_counter.most_common(5)]

    return {
        "top_hz": top_hz,
        "top_tags": top_tags,
        "active_count": len(posts),
    }


def _generate_feeling_text(agg):
    """Generate feeling text using OpenAI or fall back to template."""
    top_hz = agg["top_hz"]
    label = HZ_LABEL.get(top_hz, "Kalp merkezi")
    count = agg["active_count"]
    tags_str = ", ".join(agg["top_tags"][:3]) if agg["top_tags"] else "sessizlik"

    try:
        from app.services.ai_service import get_client
        client = get_client()
        model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()

        prompt = (
            f"You are SANRI. The collective emotional field today shows:\n"
            f"- Dominant frequency: {top_hz} Hz ({label})\n"
            f"- Active people: {count}\n"
            f"- Top feelings: {tags_str}\n\n"
            f"Write ONE poetic sentence in Turkish (max 120 chars) describing today's collective feeling.\n"
            f"Then write the same in English.\n"
            f"Return JSON only: {{\"tr\": \"...\", \"en\": \"...\"}}\n"
            f"Tone: intuitive, personal, gently provocative but soft."
        )

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Return JSON only. No markdown."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=200,
        )

        raw = (resp.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"```\s*$", "", raw).strip()
        obj = json.loads(raw)
        tr = str(obj.get("tr", "")).strip()[:200]
        en = str(obj.get("en", "")).strip()[:200]
        if tr:
            return tr, en
    except Exception as exc:
        log.warning("OpenAI feeling generation failed, using template: %s", exc)

    tr = f"Bugün kolektif alan {label} frekansında titreşiyor — {count} kişi bu histe."
    en = f"The collective field resonates at {label} today — {count} people share this feeling."
    return tr, en


def generate_daily_feeling(db: Session):
    """Main entry point — called by scheduler or cron route."""
    today = date.today()
    period = _period()

    existing = (
        db.query(DailyFeeling)
        .filter(DailyFeeling.day == today, DailyFeeling.period == period)
        .first()
    )
    if existing:
        return _row_to_dict(existing)

    agg = _aggregate_yanki(db)

    if agg and agg["active_count"] > 0:
        tr, en = _generate_feeling_text(agg)
        top_hz = agg["top_hz"]
        top_tags = agg["top_tags"]
        active_count = agg["active_count"]
    else:
        top_hz, tr, en, top_tags, active_count = _get_fallback()

    row = DailyFeeling(
        day=today,
        period=period,
        top_frequency=top_hz,
        top_tags=json.dumps(top_tags, ensure_ascii=False) if top_tags else "[]",
        active_count=active_count,
        feeling_text_tr=tr,
        feeling_text_en=en,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(DailyFeeling)
            .filter(DailyFeeling.day == today, DailyFeeling.period == period)
            .first()
        )
        if existing:
            return _row_to_dict(existing)
        raise

    return _row_to_dict(row)


def get_today_feeling(db: Session):
    """Get the latest feeling for today (prefer current period, fall back to other)."""
    today = date.today()
    period = _period()

    row = (
        db.query(DailyFeeling)
        .filter(DailyFeeling.day == today, DailyFeeling.period == period)
        .first()
    )
    if not row:
        row = (
            db.query(DailyFeeling)
            .filter(DailyFeeling.day == today)
            .order_by(DailyFeeling.created_at.desc())
            .first()
        )

    if row:
        return _row_to_dict(row)

    top_hz, tr, en, tags, count = _get_fallback()
    return {
        "day": str(today),
        "period": period,
        "top_frequency": top_hz,
        "top_tags": tags,
        "active_count": count,
        "feeling_tr": tr,
        "feeling_en": en,
        "_fallback": True,
    }


def _row_to_dict(row):
    tags = []
    if row.top_tags:
        try:
            tags = json.loads(row.top_tags)
        except Exception:
            tags = []
    return {
        "day": str(row.day),
        "period": row.period,
        "top_frequency": row.top_frequency,
        "top_tags": tags,
        "active_count": row.active_count or 0,
        "feeling_tr": row.feeling_text_tr or "",
        "feeling_en": row.feeling_text_en or "",
    }
