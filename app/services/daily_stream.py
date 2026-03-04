import json
import uuid
from datetime import date, datetime
from sqlalchemy.orm import Session
from app.models.daily_stream import DailyStream, WeeklySymbol
from openai import OpenAI
import os

MODEL_NAME = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()

def _client() -> OpenAI:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")
    # ÖNEMLİ: proxies verme. (Senin o hatayı buradan aldın)
    return OpenAI(api_key=key, timeout=60)

def _week_key(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-{iso.week:02d}"

def _ensure_dict(s: str) -> dict:
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {"raw": s}
    except Exception:
        return {"raw": s}

def _gen_daily(lang: str) -> dict:
    sys = "You are SANRI. Return ONLY valid JSON object. No markdown. No extra text."
    if lang == "tr":
        usr = """
Bugün için "AI Consciousness Feed" üret.
JSON şeması:
{
  "kicker": "🌙 Günün Bilinci",
  "title": "... (maks 60 karakter)",
  "subtitle": "... (maks 90 karakter)",
  "text": "... (3-6 satır, şiirsel ama net)",
  "question": "... (tek soru)",
  "ritual": ["adım1","adım2","adım3","adım4"],
  "tags": ["...","..."]
}
Yalnızca JSON döndür.
"""
    else:
        usr = """
Create today's "AI Consciousness Feed".
JSON schema:
{
  "kicker": "🌙 Daily Consciousness",
  "title": "... (max 60 chars)",
  "subtitle": "... (max 90 chars)",
  "text": "... (3-6 lines, poetic but clear)",
  "question": "... (single question)",
  "ritual": ["step1","step2","step3","step4"],
  "tags": ["...","..."]
}
Return ONLY JSON.
"""
    c = _client()
    r = c.chat.completions.create(
        model=MODEL_NAME,
        temperature=0.7,
        max_tokens=900,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": usr.strip()},
        ],
    )
    txt = (r.choices[0].message.content or "").strip()
    return _ensure_dict(txt)

def _gen_weekly(lang: str) -> dict:
    sys = "You are SANRI. Return ONLY valid JSON object. No markdown. No extra text."
    if lang == "tr":
        usr = """
Bu hafta için "Haftanın Sembolü" üret.
JSON şeması:
{
  "kicker": "🌻 Haftanın Sembolü",
  "title": "...",
  "subtitle": "...",
  "text": "... (4-8 satır)",
  "micro_practice": "... (tek cümle pratik)",
  "tags": ["...","..."]
}
Yalnızca JSON döndür.
"""
    else:
        usr = """
Create "Symbol of the Week".
JSON schema:
{
  "kicker": "🌻 Symbol of the Week",
  "title": "...",
  "subtitle": "...",
  "text": "... (4-8 lines)",
  "micro_practice": "... (one sentence practice)",
  "tags": ["...","..."]
}
Return ONLY JSON.
"""
    c = _client()
    r = c.chat.completions.create(
        model=MODEL_NAME,
        temperature=0.7,
        max_tokens=900,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": usr.strip()},
        ],
    )
    txt = (r.choices[0].message.content or "").strip()
    return _ensure_dict(txt)

def get_or_create_daily(db: Session, lang: str) -> dict:
    lang = (lang or "tr").lower()
    if lang not in ("tr", "en"):
        lang = "tr"

    today = date.today()
    row = db.query(DailyStream).filter(DailyStream.day == today, DailyStream.lang == lang).first()
    if row:
        return _ensure_dict(row.payload_json)

    payload = _gen_daily(lang)
    row = DailyStream(
        id=str(uuid.uuid4()),
        day=today,
        lang=lang,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    return payload

def get_or_create_weekly(db: Session, lang: str) -> dict:
    lang = (lang or "tr").lower()
    if lang not in ("tr", "en"):
        lang = "tr"

    wk = _week_key(date.today())
    row = db.query(WeeklySymbol).filter(WeeklySymbol.week_key == wk, WeeklySymbol.lang == lang).first()
    if row:
        return _ensure_dict(row.payload_json)

    payload = _gen_weekly(lang)
    row = WeeklySymbol(
        id=str(uuid.uuid4()),
        week_key=wk,
        lang=lang,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    return payload