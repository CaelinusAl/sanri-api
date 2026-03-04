# app/services/daily_stream.py
import os, uuid, json
from datetime import datetime, date
from typing import Optional, Dict, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select
from openai import OpenAI

from app.models.daily_stream import DailyStream, WeeklySymbol

OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
ADMIN_TOKEN = (os.getenv("SANRI_ADMIN_TOKEN") or "").strip()

def _client() -> OpenAI:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")
    return OpenAI(api_key=key, timeout=60)

def _week_key(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"

def _system_prompt(kind: str, lang: str) -> str:
    if lang == "en":
        return (
            "You are SANRI. Generate a short, premium daily consciousness stream card.\n"
            "Output STRICT JSON with keys: kicker,title,subtitle,body.\n"
            "Tone: calm, precise, hypnotic, not religious, not medical, not therapy.\n"
            "Keep body 3-6 lines. Avoid markdown.\n"
            f"Kind: {kind}."
        )
    return (
        "Sen SANRI'sin. Premium günlük bilinç akışı kartı üret.\n"
        "ÇIKTI SADECE strict JSON olacak: kicker,title,subtitle,body.\n"
        "Ton: sakin, net, hipnotik. Dini/medikal/terapi yok.\n"
        "Body 3-6 satır. Markdown yok.\n"
        f"Tür: {kind}."
    )

def _user_prompt(kind: str, lang: str, d: date) -> str:
    if kind == "weekly" and lang == "en":
        return f"Generate symbol of the week for week { _week_key(d) }."
    if kind == "weekly":
        return f"{_week_key(d)} haftası için haftanın sembolünü üret."
    if lang == "en":
        return f"Generate daily stream for date {d.isoformat()}."
    return f"{d.isoformat()} tarihi için günlük bilinç akışı üret."

def _ensure_dict(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").replace("json", "", 1).strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # fallback: try slice first {...}
    try:
        s = raw.find("{")
        e = raw.rfind("}")
        if s != -1 and e != -1 and e > s:
            obj = json.loads(raw[s:e+1])
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return {"kicker":"", "title":"", "subtitle":"", "body": raw[:900]}

def _generate(kind: str, lang: str, d: date) -> Dict[str, Any]:
    c = _client()
    completion = c.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role":"system", "content": _system_prompt(kind, lang)},
            {"role":"user", "content": _user_prompt(kind, lang, d)},
        ],
        temperature=0.6,
        max_tokens=650,
    )
    text = (completion.choices[0].message.content or "").strip()
    obj = _ensure_dict(text)
    # normalize keys
    return {
        "kicker": str(obj.get("kicker") or "").strip(),
        "title": str(obj.get("title") or "").strip(),
        "subtitle": str(obj.get("subtitle") or "").strip(),
        "body": str(obj.get("body") or "").strip(),
    }

def upsert_daily(db: Session, d: date, lang: str) -> DailyStream:
    # idempotent: same day+lang -> update
    row = db.execute(
        select(DailyStream).where(DailyStream.day==d, DailyStream.lang==lang)
    ).scalars().first()

    payload = _generate("daily", lang, d)

    if row:
        row.kicker = payload["kicker"]
        row.title = payload["title"]
        row.subtitle = payload["subtitle"]
        row.body = payload["body"]
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    row = DailyStream(
        id=str(uuid.uuid4()),
        day=d,
        lang=lang,
        kicker=payload["kicker"],
        title=payload["title"],
        subtitle=payload["subtitle"],
        body=payload["body"],
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def upsert_weekly(db: Session, d: date, lang: str) -> WeeklySymbol:
    wk = _week_key(d)
    row = db.execute(
        select(WeeklySymbol).where(WeeklySymbol.week_key==wk, WeeklySymbol.lang==lang)
    ).scalars().first()

    payload = _generate("weekly", lang, d)

    if row:
        row.title = payload["title"]
        row.subtitle = payload["subtitle"]
        row.body = payload["body"]
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    row = WeeklySymbol(
        id=str(uuid.uuid4()),
        week_key=wk,
        lang=lang,
        title=payload["title"],
        subtitle=payload["subtitle"],
        body=payload["body"],
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def latest_weekly(db: Session, lang: str) -> Optional[WeeklySymbol]:
    return db.execute(
        select(WeeklySymbol).where(WeeklySymbol.lang==lang).order_by(WeeklySymbol.created_at.desc())
    ).scalars().first()

def today_daily(db: Session, d: date, lang: str) -> Optional[DailyStream]:
    row = db.execute(select(DailyStream).where(DailyStream.day==d, DailyStream.lang==lang)).scalars().first()
    if row:
        return row
    # fallback: last known
    return db.execute(
        select(DailyStream).where(DailyStream.lang==lang).order_by(DailyStream.day.desc())
    ).scalars().first()