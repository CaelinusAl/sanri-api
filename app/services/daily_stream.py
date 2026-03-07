# app/services/daily_stream.py
import json
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.content import DailyStream, WeeklySymbol
from app.routes.bilinc_alani import get_client
import os

def _week_key(d: date) -> str:
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-{iso_week:02d}"

def _safe_json_dumps(x) -> str:
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return "[]"

def generate_daily(lang: str) -> dict:
    """
    LLM’den JSON üretir.
    """
    client = get_client()
    model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()

    prompt = (
        "You are SANRI. Produce a DAILY CONSCIOUSNESS STREAM.\n"
        "Return ONLY valid JSON object.\n"
        "Schema:\n"
        "{\n"
        ' "title": "...",\n'
        ' "short": "...",\n'
        ' "message": "...",\n'
        ' "tags": ["...","..."]\n'
        "}\n"
        f"Language: {lang}\n"
        "Style: hypnotic, clean, premium, short paragraphs.\n"
        "No markdown. No backticks.\n"
    )

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=900,
    )

    raw = (completion.choices[0].message.content or "").strip()
    j = ensure_json_obj(raw)

    # normalize
    title = str(j.get("title") or "").strip() or ("Günlük Akış" if lang == "tr" else "Daily Stream")
    short = str(j.get("short") or "").strip()
    message = str(j.get("message") or "").strip() or ( "Bugün merkezde kal." if lang=="tr" else "Stay centered today." )
    tags = j.get("tags") if isinstance(j.get("tags"), list) else []

    return {"title": title, "short": short, "message": message, "tags": tags}

def generate_weekly(lang: str) -> dict:
    client = get_client()
    model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()

    prompt = (
        "You are SANRI. Produce WEEKLY SYMBOL OF THE WEEK.\n"
        "Return ONLY valid JSON object.\n"
        "Schema:\n"
        "{\n"
        ' "title": "...",\n'
        ' "subtitle": "...",\n'
        ' "reading": "...",\n'
        ' "tags": ["...","..."]\n'
        "}\n"
        f"Language: {lang}\n"
        "Tone: sacred+futuristic, clear.\n"
        "No markdown. No backticks.\n"
    )

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.75,
        max_tokens=1100,
    )

    raw = (completion.choices[0].message.content or "").strip()
    j = ensure_json_obj(raw)

    title = str(j.get("title") or "").strip() or ("Haftanın Sembolü" if lang=="tr" else "Symbol of the Week")
    subtitle = str(j.get("subtitle") or "").strip()
    reading = str(j.get("reading") or "").strip() or ( "Bu hafta merkez." if lang=="tr" else "This week: center." )
    tags = j.get("tags") if isinstance(j.get("tags"), list) else []

    return {"title": title, "subtitle": subtitle, "reading": reading, "tags": tags}

def get_or_create_daily(db: Session, lang: str) -> dict:
    d = date.today()
    row = db.query(DailyStream).filter(DailyStream.day == d, DailyStream.lang == lang).first()
    if row:
        return {
            "day": str(row.day),
            "lang": row.lang,
            "title": row.title,
            "short": row.short,
            "message": row.message,
            "tags": json.loads(row.tags) if row.tags else [],
        }

    g = generate_daily(lang)

    row = DailyStream(
        day=d,
        lang=lang,
        title=g["title"],
        short=g["short"],
        message=g["message"],
        tags=_safe_json_dumps(g["tags"]),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # yarış olursa tekrar çek
        row = db.query(DailyStream).filter(DailyStream.day == d, DailyStream.lang == lang).first()
        if row:
            return {
                "day": str(row.day),
                "lang": row.lang,
                "title": row.title,
                "short": row.short,
                "message": row.message,
                "tags": json.loads(row.tags) if row.tags else [],
            }
        raise

    return {
        "day": str(row.day),
        "lang": row.lang,
        "title": row.title,
        "short": row.short,
        "message": row.message,
        "tags": g["tags"],
    }

def get_or_create_weekly(db: Session, lang: str) -> dict:
    d = date.today()
    wk = _week_key(d)

    row = db.query(WeeklySymbol).filter(WeeklySymbol.week_key == wk, WeeklySymbol.lang == lang).first()
    if row:
        return {
            "week": row.week_key,
            "lang": row.lang,
            "title": row.title,
            "subtitle": row.subtitle,
            "reading": row.reading,
            "tags": json.loads(row.tags) if row.tags else [],
        }

    g = generate_weekly(lang)
    row = WeeklySymbol(
        week_key=wk,
        lang=lang,
        title=g["title"],
        subtitle=g["subtitle"],
        reading=g["reading"],
        tags=_safe_json_dumps(g["tags"]),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.query(WeeklySymbol).filter(WeeklySymbol.week_key == wk, WeeklySymbol.lang == lang).first()
        if row:
            return {
                "week": row.week_key,
                "lang": row.lang,
                "title": row.title,
                "subtitle": row.subtitle,
                "reading": row.reading,
                "tags": json.loads(row.tags) if row.tags else [],
            }
        raise

    return {
        "week": row.week_key,
        "lang": row.lang,
        "title": row.title,
        "subtitle": row.subtitle,
        "reading": row.reading,
        "tags": g["tags"],
    }