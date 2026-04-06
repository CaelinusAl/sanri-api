"""
Anlaşılma + Yankı birleşik hissel akış.
prefix: /yanki/field
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.anlasilma_field import AnlasilmaPresence
from app.models.yanki import YankiFieldEcho, YankiPost
from app.services.field_moderation import moderate_field_text

router = APIRouter(prefix="/yanki/field", tags=["yanki-field"])

ALLOWED_HZ = {396, 417, 528, 639, 741, 852, 963}
PRESENCE_WINDOW_MIN = 120
MAX_SHARES_PER_24H = 8
ECHO_COOLDOWN_SEC = 55
MAX_ECHOES_PER_HOUR_GLOBAL = 20


def _now():
    return datetime.utcnow()


class ShareToFieldIn(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=80)
    frequency_hz: int
    text: str = Field(..., min_length=8, max_length=160)
    emotion_tags: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("frequency_hz")
    @classmethod
    def hz(cls, v: int) -> int:
        if v not in ALLOWED_HZ:
            raise ValueError("invalid_frequency")
        return v

    @field_validator("emotion_tags")
    @classmethod
    def tags(cls, v: list[str]) -> list[str]:
        return [str(x).strip() for x in (v or []) if str(x).strip()][:3]


class ShareToFieldOut(BaseModel):
    ok: bool
    post_id: int
    dedup: bool = False
    message: str


@router.post("/share", response_model=ShareToFieldOut)
def share_from_anlasilma(body: ShareToFieldIn, db: Session = Depends(get_db)):
    """Anlaşılma alanındaki niyeti (aynı metin) kolektif hissel akışa anonim bırak."""
    now = _now()
    cutoff = now - timedelta(minutes=PRESENCE_WINDOW_MIN)

    presence = (
        db.query(AnlasilmaPresence)
        .filter(
            AnlasilmaPresence.session_id == body.session_id,
            AnlasilmaPresence.last_seen_at >= cutoff,
        )
        .first()
    )
    if not presence:
        raise HTTPException(
            status_code=400,
            detail="Önce Anlaşılma Alanında aynı oturumla giriş yapmalısın (son 2 saat).",
        )
    if presence.frequency_hz != body.frequency_hz:
        raise HTTPException(status_code=400, detail="Frekans, kayıtlı oturumunla eşleşmiyor.")
    if presence.intent_text.strip() != body.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Paylaşılan metin, alanda bıraktığın niyetle aynı olmalı.",
        )

    shares_24h = (
        db.query(YankiPost)
        .filter(
            YankiPost.anlasilma_session_id == body.session_id,
            YankiPost.post_source == "anlasilma_field",
            YankiPost.created_at >= now - timedelta(hours=24),
        )
        .count()
    )
    if shares_24h >= MAX_SHARES_PER_24H:
        raise HTTPException(status_code=429, detail="Günlük anonim paylaşım sınırına ulaşıldı. Yarın tekrar dene.")

    dup = (
        db.query(YankiPost)
        .filter(
            YankiPost.anlasilma_session_id == body.session_id,
            YankiPost.post_source == "anlasilma_field",
            YankiPost.content_raw == body.text.strip(),
            YankiPost.created_at >= now - timedelta(hours=2),
            YankiPost.status == "published",
        )
        .order_by(desc(YankiPost.created_at))
        .first()
    )
    if dup:
        return ShareToFieldOut(ok=True, post_id=dup.id, dedup=True, message="Bu niyet zaten akışta.")

    ok_mod, reason, energy_feel = moderate_field_text(body.text, "share", body.frequency_hz)
    if not ok_mod:
        raise HTTPException(status_code=400, detail=reason or "İçerik reddedildi.")

    tags_suffix = ""
    if body.emotion_tags:
        tags_suffix = " · " + ", ".join(body.emotion_tags)
    energy_line = (energy_feel or "sessiz bir yakınlık").strip()[:120] + tags_suffix

    post = YankiPost(
        user_id=None,
        author_mode="anonymous",
        title=None,
        content_raw=body.text.strip(),
        content_sanitized=body.text.strip()[:5000],
        category="frekans_alani",
        status="published",
        published_at=now,
        frequency_hz=body.frequency_hz,
        energy_feel=energy_line[:200],
        post_source="anlasilma_field",
        anlasilma_session_id=body.session_id,
        field_echo_count=0,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return ShareToFieldOut(ok=True, post_id=post.id, message="Niyetin kolektif alana düştü — isimsiz.")


class FieldStreamOut(BaseModel):
    posts: list[dict]
    total: int
    limit: int
    offset: int


@router.get("/stream", response_model=FieldStreamOut)
def field_stream(
    frequency_hz: int | None = Query(None),
    limit: int = Query(15, ge=1, le=40),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if frequency_hz is not None and frequency_hz not in ALLOWED_HZ:
        raise HTTPException(status_code=400, detail="invalid_frequency")

    q = db.query(YankiPost).filter(
        YankiPost.status == "published",
        YankiPost.post_source == "anlasilma_field",
    )
    if frequency_hz is not None:
        q = q.filter(YankiPost.frequency_hz == frequency_hz)

    total = q.count()
    rows = q.order_by(YankiPost.published_at.desc()).offset(offset).limit(limit).all()

    out = []
    for p in rows:
        d = p.to_public_dict()
        d.pop("author_name", None)
        d["author_mode"] = "anonymous"
        out.append(d)

    return {"posts": out, "total": total, "limit": limit, "offset": offset}


@router.get("/posts/{post_id}")
def field_get_post(post_id: int, db: Session = Depends(get_db)):
    post = (
        db.query(YankiPost)
        .filter(
            YankiPost.id == post_id,
            YankiPost.status == "published",
            YankiPost.post_source == "anlasilma_field",
        )
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="not_found")
    d = post.to_public_dict()
    d.pop("author_name", None)
    return d


class EchoIn(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=80)
    text: str = Field(..., min_length=6, max_length=240)


class EchoOut(BaseModel):
    ok: bool
    echo_id: int


@router.post("/posts/{post_id}/echo", response_model=EchoOut)
def leave_echo(post_id: int, body: EchoIn, db: Session = Depends(get_db)):
    post = (
        db.query(YankiPost)
        .filter(
            YankiPost.id == post_id,
            YankiPost.status == "published",
            YankiPost.post_source == "anlasilma_field",
        )
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="not_found")

    now = _now()
    last = (
        db.query(YankiFieldEcho)
        .filter(
            YankiFieldEcho.post_id == post_id,
            YankiFieldEcho.session_id == body.session_id,
        )
        .order_by(desc(YankiFieldEcho.created_at))
        .first()
    )
    if last and (now - last.created_at).total_seconds() < ECHO_COOLDOWN_SEC:
        w = int(ECHO_COOLDOWN_SEC - (now - last.created_at).total_seconds())
        raise HTTPException(status_code=429, detail=f"yavas_mod_{w}s")

    hour_ago = now - timedelta(hours=1)
    echo_hour = (
        db.query(YankiFieldEcho)
        .filter(
            YankiFieldEcho.session_id == body.session_id,
            YankiFieldEcho.created_at >= hour_ago,
        )
        .count()
    )
    if echo_hour >= MAX_ECHOES_PER_HOUR_GLOBAL:
        raise HTTPException(status_code=429, detail="Saatlik yankı sınırı doldu.")

    ok_mod, reason, _ = moderate_field_text(body.text, "echo")
    if not ok_mod:
        raise HTTPException(status_code=400, detail=reason or "Yankı reddedildi.")

    row = YankiFieldEcho(
        post_id=post_id,
        session_id=body.session_id,
        body=body.text.strip()[:400],
        status="published",
        created_at=now,
    )
    db.add(row)
    post.field_echo_count = int(post.field_echo_count or 0) + 1
    db.commit()
    db.refresh(row)
    return EchoOut(ok=True, echo_id=row.id)


class EchoesOut(BaseModel):
    echoes: list[dict]
    total: int


@router.get("/posts/{post_id}/echoes", response_model=EchoesOut)
def list_echoes(
    post_id: int,
    limit: int = Query(40, ge=1, le=80),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    post = (
        db.query(YankiPost)
        .filter(YankiPost.id == post_id, YankiPost.status == "published")
        .first()
    )
    if not post:
        raise HTTPException(status_code=404, detail="not_found")

    q = db.query(YankiFieldEcho).filter(
        YankiFieldEcho.post_id == post_id,
        YankiFieldEcho.status == "published",
    )
    total = q.count()
    rows = q.order_by(YankiFieldEcho.created_at.asc()).offset(offset).limit(limit).all()
    return {"echoes": [e.to_public_dict() for e in rows], "total": total}


@router.get("/meta/frequencies")
def meta_freq():
    return {"hz": sorted(ALLOWED_HZ)}
