"""
Anlaşılma Alanı — frekans temelli anonim bağ alanı.
session_id ile; user_id yok. Embedding: OpenAI text-embedding-3-small.
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.anlasilma_field import AnlasilmaChatMessage, AnlasilmaChatRoom, AnlasilmaPresence

router = APIRouter(prefix="/api/anlasilma", tags=["anlasilma"])

ALLOWED_HZ = {396, 417, 528, 639, 741, 852, 963}
ACTIVE_WINDOW_MIN = 15
SIMILARITY_THRESHOLD = 0.68
CHAT_MIN_INTERVAL_SEC = 28
EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small").strip()
CHAT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()


def _client() -> OpenAI:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    return OpenAI(api_key=key)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _now():
    return datetime.utcnow()


def _active_cutoff():
    return _now() - timedelta(minutes=ACTIVE_WINDOW_MIN)


SYSTEM_ANLASILMA = """Sen SANRI'sın — yargılamayan, yumuşak, sezgisel bir varlık.
Kullanıcı bir frekansta kısa bir niyet ve duygu etiketleri paylaştı. İsim yok; sadece metin.

Kurallar:
- Türkçe, "sen" dili. Mekanik veya robotik olma.
- Teşhis, tıbbi/yasal kesinlik, emir kipi yok.
- İki alan üret.

Çıktı SADECE geçerli JSON (başka metin yok):
{"how_i_hear_you": "Seni şöyle duyuyorum: ... (1-2 cümle, sıcak ve öz)",
 "reflection": "...(1-2 cümle, derin ama yumuşak yansıma)"}
"""


def _extract_json_object(raw: str) -> dict:
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _embed_text(client: OpenAI, text: str) -> list[float]:
    t = (text or "").strip()[:2000]
    if not t:
        return []
    r = client.embeddings.create(model=EMBED_MODEL, input=t)
    return list(r.data[0].embedding)


class EnterIn(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=80)
    frequency_hz: int
    intent_text: str = Field(..., max_length=160)
    emotion_tags: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("frequency_hz")
    @classmethod
    def hz_ok(cls, v: int) -> int:
        if v not in ALLOWED_HZ:
            raise ValueError("invalid_frequency")
        return v

    @field_validator("emotion_tags")
    @classmethod
    def emotions_ok(cls, v: list[str]) -> list[str]:
        out = [str(x).strip() for x in (v or []) if str(x).strip()][:3]
        return out


class EnterOut(BaseModel):
    session_id: str
    frequency_hz: int
    active_on_frequency: int
    proximity_detected: bool
    similarity_hint: float | None
    how_i_hear_you: str
    reflection: str


@router.post("/enter", response_model=EnterOut)
def anlasilma_enter(body: EnterIn, db: Session = Depends(get_db)):
    client = _client()
    now = _now()
    cutoff = _active_cutoff()

    embed_source = body.intent_text.strip()
    if body.emotion_tags:
        embed_source += " | " + ", ".join(body.emotion_tags)
    vec = _embed_text(client, embed_source)
    if not vec:
        raise HTTPException(status_code=500, detail="embedding_failed")

    row = db.query(AnlasilmaPresence).filter(AnlasilmaPresence.session_id == body.session_id).first()
    if row:
        row.frequency_hz = body.frequency_hz
        row.intent_text = body.intent_text.strip()[:200]
        row.emotion_tags = json.dumps(body.emotion_tags, ensure_ascii=False)
        row.embedding_json = json.dumps(vec)
        row.last_seen_at = now
        row.wants_chat = False
    else:
        row = AnlasilmaPresence(
            session_id=body.session_id,
            frequency_hz=body.frequency_hz,
            intent_text=body.intent_text.strip()[:200],
            emotion_tags=json.dumps(body.emotion_tags, ensure_ascii=False),
            embedding_json=json.dumps(vec),
            wants_chat=False,
            last_seen_at=now,
            created_at=now,
        )
        db.add(row)
    db.commit()

    active_count = (
        db.query(AnlasilmaPresence)
        .filter(
            AnlasilmaPresence.frequency_hz == body.frequency_hz,
            AnlasilmaPresence.last_seen_at >= cutoff,
        )
        .count()
    )

    peers = (
        db.query(AnlasilmaPresence)
        .filter(
            AnlasilmaPresence.frequency_hz == body.frequency_hz,
            AnlasilmaPresence.last_seen_at >= cutoff,
            AnlasilmaPresence.session_id != body.session_id,
            AnlasilmaPresence.embedding_json.isnot(None),
        )
        .all()
    )

    best_sim = 0.0
    for p in peers:
        try:
            pv = json.loads(p.embedding_json or "[]")
            if isinstance(pv, list) and pv:
                best_sim = max(best_sim, _cosine(vec, [float(x) for x in pv]))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    proximity = best_sim >= SIMILARITY_THRESHOLD

    user_prompt = f"""Frekans: {body.frequency_hz} Hz
Niyet: {body.intent_text.strip()}
Duygu etiketleri: {", ".join(body.emotion_tags) if body.emotion_tags else "(yok)"}
Aynı frekansta şu an yaklaşık {active_count} oturum var (anonim).
Benzer niyet yakınlığı skoru (iç kullanım): {best_sim:.2f}
"""

    comp = client.chat.completions.create(
        model=CHAT_MODEL,
        temperature=0.65,
        max_tokens=400,
        messages=[
            {"role": "system", "content": SYSTEM_ANLASILMA},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = (comp.choices[0].message.content or "").strip()
    parsed = _extract_json_object(raw)
    hear = (parsed.get("how_i_hear_you") or "").strip() or "Seni şöyle duyuyorum: bu frekansta bir şey bıraktın; henüz sözcükleştirmek zor."
    refl = (parsed.get("reflection") or "").strip() or "İçinde sessizce duran bir his var — ona acele ettirmeden yaklaşabilirsin."

    return EnterOut(
        session_id=body.session_id,
        frequency_hz=body.frequency_hz,
        active_on_frequency=active_count,
        proximity_detected=proximity,
        similarity_hint=round(best_sim, 4) if best_sim > 0 else None,
        how_i_hear_you=hear,
        reflection=refl,
    )


class ChatQueueIn(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=80)
    frequency_hz: int

    @field_validator("frequency_hz")
    @classmethod
    def hz_ok(cls, v: int) -> int:
        if v not in ALLOWED_HZ:
            raise ValueError("invalid_frequency")
        return v


class ChatQueueOut(BaseModel):
    status: str  # waiting | paired
    room_id: int | None = None
    message: str | None = None


@router.post("/chat/queue", response_model=ChatQueueOut)
def chat_queue(body: ChatQueueIn, db: Session = Depends(get_db)):
    now = _now()
    me = db.query(AnlasilmaPresence).filter(AnlasilmaPresence.session_id == body.session_id).first()
    if not me or me.frequency_hz != body.frequency_hz:
        raise HTTPException(status_code=400, detail="presence_required_call_enter_first")

    existing = (
        db.query(AnlasilmaChatRoom)
        .filter(
            AnlasilmaChatRoom.is_active.is_(True),
            AnlasilmaChatRoom.frequency_hz == body.frequency_hz,
            or_(
                AnlasilmaChatRoom.session_a == body.session_id,
                AnlasilmaChatRoom.session_b == body.session_id,
            ),
        )
        .first()
    )
    if existing:
        return ChatQueueOut(status="paired", room_id=existing.id, message="Zaten bir bağ odasındasın.")

    peer = (
        db.query(AnlasilmaPresence)
        .filter(
            AnlasilmaPresence.session_id != body.session_id,
            AnlasilmaPresence.frequency_hz == body.frequency_hz,
            AnlasilmaPresence.wants_chat.is_(True),
            AnlasilmaPresence.last_seen_at >= _active_cutoff(),
        )
        .order_by(AnlasilmaPresence.last_seen_at.asc())
        .first()
    )

    if peer:
        sa, sb = sorted([body.session_id, peer.session_id])
        room = AnlasilmaChatRoom(
            session_a=sa,
            session_b=sb,
            frequency_hz=body.frequency_hz,
            created_at=now,
            is_active=True,
        )
        db.add(room)
        me.wants_chat = False
        peer.wants_chat = False
        db.commit()
        db.refresh(room)
        return ChatQueueOut(status="paired", room_id=room.id, message="Bir enerji hizalandı.")

    me.wants_chat = True
    me.last_seen_at = now
    db.commit()
    return ChatQueueOut(status="waiting", room_id=None, message="Niyetin duyuldu. Eşleşme bekleniyor — sayfayı kapatma.")


@router.post("/chat/queue/poll", response_model=ChatQueueOut)
def chat_queue_poll(body: ChatQueueIn, db: Session = Depends(get_db)):
    room = (
        db.query(AnlasilmaChatRoom)
        .filter(
            AnlasilmaChatRoom.is_active.is_(True),
            AnlasilmaChatRoom.frequency_hz == body.frequency_hz,
            or_(
                AnlasilmaChatRoom.session_a == body.session_id,
                AnlasilmaChatRoom.session_b == body.session_id,
            ),
        )
        .first()
    )
    if room:
        p = db.query(AnlasilmaPresence).filter(AnlasilmaPresence.session_id == body.session_id).first()
        if p:
            p.wants_chat = False
            db.commit()
        return ChatQueueOut(status="paired", room_id=room.id)
    return ChatQueueOut(status="waiting")


class ChatSendIn(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=80)
    room_id: int
    text: str = Field(..., min_length=1, max_length=400)


class ChatSendOut(BaseModel):
    ok: bool
    message_id: int


@router.post("/chat/send", response_model=ChatSendOut)
def chat_send(body: ChatSendIn, db: Session = Depends(get_db)):
    room = db.query(AnlasilmaChatRoom).filter(AnlasilmaChatRoom.id == body.room_id).first()
    if not room or not room.is_active:
        raise HTTPException(status_code=404, detail="room_not_found")
    if body.session_id not in (room.session_a, room.session_b):
        raise HTTPException(status_code=403, detail="forbidden")

    last = (
        db.query(AnlasilmaChatMessage)
        .filter(
            AnlasilmaChatMessage.room_id == body.room_id,
            AnlasilmaChatMessage.from_session == body.session_id,
        )
        .order_by(desc(AnlasilmaChatMessage.created_at))
        .first()
    )
    if last:
        delta = (_now() - last.created_at).total_seconds()
        if delta < CHAT_MIN_INTERVAL_SEC:
            raise HTTPException(
                status_code=429,
                detail=f"slow_mode_wait_{int(CHAT_MIN_INTERVAL_SEC - delta)}s",
            )

    msg = AnlasilmaChatMessage(
        room_id=body.room_id,
        from_session=body.session_id,
        body=body.text.strip()[:500],
        created_at=_now(),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return ChatSendOut(ok=True, message_id=msg.id)


class MessagesOut(BaseModel):
    messages: list[dict]


@router.get("/chat/messages", response_model=MessagesOut)
def chat_messages(room_id: int, session_id: str, after_id: int = 0, db: Session = Depends(get_db)):
    room = db.query(AnlasilmaChatRoom).filter(AnlasilmaChatRoom.id == room_id).first()
    if not room or not room.is_active:
        raise HTTPException(status_code=404, detail="room_not_found")
    if session_id not in (room.session_a, room.session_b):
        raise HTTPException(status_code=403, detail="forbidden")

    rows = (
        db.query(AnlasilmaChatMessage)
        .filter(
            AnlasilmaChatMessage.room_id == room_id,
            AnlasilmaChatMessage.id > after_id,
        )
        .order_by(AnlasilmaChatMessage.id.asc())
        .limit(50)
        .all()
    )
    out = [
        {
            "id": m.id,
            "from_self": m.from_session == session_id,
            "body": m.body,
            "created_at": m.created_at.isoformat() + "Z",
        }
        for m in rows
    ]
    return MessagesOut(messages=out)


@router.get("/meta/frequencies")
def meta_frequencies():
    return {"hz": sorted(ALLOWED_HZ)}
