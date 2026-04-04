"""
Kişisel teslimatlar (Matrix Rol vb.) — kullanıcıya özel metinler.

- GET /deliverables/my — JWT ile kendi kayıtları
- POST /admin/deliverables — admin JWT ile oluştur / güncelle (email → user_id çözülür)
- GET /admin/deliverables — admin listesi
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.db import get_db, engine
from app.services.auth import decode_token

router = APIRouter(tags=["deliverables"])
admin_router = APIRouter(prefix="/admin", tags=["admin-deliverables"])


def _is_pg() -> bool:
    return engine.dialect.name == "postgresql"


def _ensure_deliverables_table():
    is_pg = _is_pg()
    with engine.begin() as conn:
        if is_pg:
            conn.execute(
                sa_text("""
                CREATE TABLE IF NOT EXISTS user_deliverables (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    email VARCHAR(255) NOT NULL,
                    content_id VARCHAR(120) NOT NULL,
                    product_name VARCHAR(255),
                    title VARCHAR(500),
                    card_title VARCHAR(300),
                    preview_text TEXT,
                    price_note VARCHAR(80),
                    payload_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT uq_deliverable_email_content UNIQUE (email, content_id)
                )
                """)
            )
        else:
            conn.execute(
                sa_text("""
                CREATE TABLE IF NOT EXISTS user_deliverables (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    email VARCHAR(255) NOT NULL,
                    content_id VARCHAR(120) NOT NULL,
                    product_name VARCHAR(255),
                    title VARCHAR(500),
                    card_title VARCHAR(300),
                    preview_text TEXT,
                    price_note VARCHAR(80),
                    payload_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(email, content_id)
                )
                """)
            )


try:
    _ensure_deliverables_table()
except Exception as e:
    print("[deliverables] migration:", e)


def _norm_email(e: str) -> str:
    return (e or "").strip().lower()


def _get_user_id_by_email(db: Session, email: str) -> Optional[int]:
    row = db.execute(
        sa_text("SELECT id FROM users WHERE lower(trim(email)) = :em LIMIT 1"),
        {"em": _norm_email(email)},
    ).mappings().first()
    return int(row["id"]) if row else None


def _require_user_jwt(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.replace("Bearer ", "").strip()
    payload = decode_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token")
    uid = int(payload["sub"])
    row = db.execute(
        sa_text("SELECT id, email, role FROM users WHERE id = :uid LIMIT 1"),
        {"uid": uid},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(row)


def _require_admin_jwt(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    u = _require_user_jwt(authorization, db)
    if u.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return u


def _row_to_item(row) -> dict[str, Any]:
    raw = row.get("payload_json") or "{}"
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        payload = {}
    return {
        "id": row["id"],
        "user_id": row.get("user_id"),
        "email": row.get("email"),
        "content_id": row.get("content_id"),
        "product_name": row.get("product_name"),
        "title": row.get("title"),
        "card_title": row.get("card_title"),
        "preview_text": row.get("preview_text"),
        "price_note": row.get("price_note"),
        "payload": payload,
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
    }


# ── User ─────────────────────────────────────────


@router.get("/deliverables/my")
def list_my_deliverables(
    db: Session = Depends(get_db),
    user: dict = Depends(_require_user_jwt),
):
    em = _norm_email(user.get("email") or "")
    uid = user["id"]
    rows = db.execute(
        sa_text("""
            SELECT * FROM user_deliverables
            WHERE user_id = :uid OR lower(trim(email)) = :em
            ORDER BY updated_at DESC
        """),
        {"uid": uid, "em": em},
    ).mappings().all()
    return {"items": [_row_to_item(r) for r in rows]}


# ── Admin ───────────────────────────────────────


class DeliverableSectionIn(BaseModel):
    heading: str
    body: str


class AdminDeliverableUpsert(BaseModel):
    email: EmailStr
    customer_name: str = ""
    content_id: str = "role_unlock"
    product_name: str = "Matrix Rol Okuma"
    title: str
    card_title: str = ""
    preview_text: str = ""
    price_note: str = ""
    birth_date: str = ""
    sections: list[DeliverableSectionIn] = Field(default_factory=list)
    summary_lines: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


@admin_router.post("/deliverables")
def admin_upsert_deliverable(
    body: AdminDeliverableUpsert,
    db: Session = Depends(get_db),
    _admin: dict = Depends(_require_admin_jwt),
):
    email = _norm_email(str(body.email))
    uid = _get_user_id_by_email(db, email)

    payload = {
        "content_id": body.content_id,
        "title": body.title,
        "customer_name": body.customer_name,
        "customer_email": email,
        "product_name": body.product_name,
        "birth_date": body.birth_date,
        "sections": [s.model_dump() for s in body.sections],
        "summary_lines": body.summary_lines,
        **body.extra,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    now = datetime.utcnow()

    if _is_pg():
        db.execute(
            sa_text("""
                INSERT INTO user_deliverables (
                    user_id, email, content_id, product_name, title, card_title, preview_text,
                    price_note, payload_json, created_at, updated_at
                ) VALUES (
                    :uid, :email, :cid, :pn, :title, :ct, :pv, :price, :pj, :now, :now2
                )
                ON CONFLICT (email, content_id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    product_name = EXCLUDED.product_name,
                    title = EXCLUDED.title,
                    card_title = EXCLUDED.card_title,
                    preview_text = EXCLUDED.preview_text,
                    price_note = EXCLUDED.price_note,
                    payload_json = EXCLUDED.payload_json,
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "uid": uid,
                "email": email,
                "cid": body.content_id,
                "pn": body.product_name,
                "title": body.title,
                "ct": body.card_title or body.title,
                "pv": body.preview_text,
                "price": body.price_note or None,
                "pj": payload_json,
                "now": now,
                "now2": now,
            },
        )
    else:
        db.execute(
            sa_text("""
                INSERT INTO user_deliverables (
                    user_id, email, content_id, product_name, title, card_title, preview_text,
                    price_note, payload_json, created_at, updated_at
                ) VALUES (
                    :uid, :email, :cid, :pn, :title, :ct, :pv, :price, :pj, :now, :now2
                )
                ON CONFLICT(email, content_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    product_name = excluded.product_name,
                    title = excluded.title,
                    card_title = excluded.card_title,
                    preview_text = excluded.preview_text,
                    price_note = excluded.price_note,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
            """),
            {
                "uid": uid,
                "email": email,
                "cid": body.content_id,
                "pn": body.product_name,
                "title": body.title,
                "ct": body.card_title or body.title,
                "pv": body.preview_text,
                "price": body.price_note or None,
                "pj": payload_json,
                "now": now,
                "now2": now,
            },
        )
    db.commit()

    row = db.execute(
        sa_text("""
            SELECT * FROM user_deliverables
            WHERE lower(trim(email)) = :em AND content_id = :cid
            LIMIT 1
        """),
        {"em": email, "cid": body.content_id},
    ).mappings().first()

    return {
        "ok": True,
        "linked_user_id": uid,
        "message": "Deliverable saved" if uid else "Deliverable saved (user_id null — e-posta hesaba bağlı değil)",
        "item": _row_to_item(row) if row else None,
    }


@admin_router.get("/deliverables")
def admin_list_deliverables(
    db: Session = Depends(get_db),
    _admin: dict = Depends(_require_admin_jwt),
    email: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    if email:
        rows = db.execute(
            sa_text("""
                SELECT * FROM user_deliverables
                WHERE lower(trim(email)) = :em
                ORDER BY updated_at DESC LIMIT :lim
            """),
            {"em": _norm_email(email), "lim": limit},
        ).mappings().all()
    else:
        rows = db.execute(
            sa_text("""
                SELECT * FROM user_deliverables
                ORDER BY updated_at DESC LIMIT :lim
            """),
            {"lim": limit},
        ).mappings().all()
    return {"items": [_row_to_item(r) for r in rows], "count": len(rows)}
