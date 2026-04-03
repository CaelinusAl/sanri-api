"""
Havale / EFT — manuel onaylı alternatif ödeme.
Shopier satın alma tablosu (shopier_purchases) ile aynı content_id / check akışı.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import random
import re
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db, engine
from app.routes.admin import _require_jwt

logger = logging.getLogger("bank_transfer")

router = APIRouter(prefix="/bank-transfer", tags=["bank-transfer"])
admin_router = APIRouter(prefix="/admin/bank-transfers", tags=["admin-bank-transfers"])

# ── Banka bilgileri (Railway env) ──
BANK_IBAN = os.getenv("BANK_TRANSFER_IBAN", "").strip()
BANK_RECIPIENT = os.getenv("BANK_TRANSFER_RECIPIENT_NAME", "").strip()
BANK_NAME = os.getenv("BANK_TRANSFER_BANK_NAME", "").strip()
BANK_IBAN_LABEL = os.getenv("BANK_TRANSFER_IBAN_LABEL", "SANRI — TRY").strip()

MAX_RECEIPT_BYTES = int(os.getenv("BANK_TRANSFER_MAX_RECEIPT_BYTES", str(1_500_000)))

# content_id → havale kodu öneki, tutar, ürün adı (istemci tutarı değiştiremesin)
BANK_PRODUCT_CATALOG: dict[str, dict[str, Any]] = {
    "role_unlock": {
        "prefix": "ROL",
        "amount": Decimal("369"),
        "product_name": "Matrix Rol Okuma — Tam Analiz",
    },
    "ankod_unlock": {
        "prefix": "ANKOD",
        "amount": Decimal("99"),
        "product_name": "AN_KOD — Tam Analiz",
    },
    "kod_egitmeni": {
        "prefix": "KOD",
        "amount": Decimal("999"),
        "product_name": "SANRI Kod Okuma Sistemi™ — Tam Erişim",
    },
    "kod_giris_ders": {
        "prefix": "KG",
        "amount": Decimal("47"),
        "product_name": "Kod Öğrenmeye Giriş — Canlı Ders",
    },
}

_TRANSFER_CODE_RE = re.compile(r"^[A-Z0-9]+-\d{4}$")


def _is_pg() -> bool:
    return engine.dialect.name == "postgresql"


def _ensure_bank_transfer_table():
    with engine.connect() as conn:
        if _is_pg():
            conn.execute(
                sa_text("""
                CREATE TABLE IF NOT EXISTS bank_transfer_requests (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    product_name VARCHAR(500) NOT NULL,
                    content_id VARCHAR(120) NOT NULL,
                    amount NUMERIC(12, 2) NOT NULL,
                    iban_label VARCHAR(120),
                    transfer_code VARCHAR(32) NOT NULL,
                    receipt_file_url TEXT,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    admin_note TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            )
            conn.execute(
                sa_text("""
                CREATE UNIQUE INDEX IF NOT EXISTS ix_btr_transfer_code
                ON bank_transfer_requests (transfer_code)
            """)
            )
        else:
            conn.execute(
                sa_text("""
                CREATE TABLE IF NOT EXISTS bank_transfer_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    product_name VARCHAR(500) NOT NULL,
                    content_id VARCHAR(120) NOT NULL,
                    amount REAL NOT NULL,
                    iban_label VARCHAR(120),
                    transfer_code VARCHAR(32) NOT NULL UNIQUE,
                    receipt_file_url TEXT,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    admin_note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            )
        conn.commit()


try:
    _ensure_bank_transfer_table()
except Exception as e:
    logger.warning("bank_transfer table migration: %s", e)


def _catalog_entry(content_id: str) -> dict[str, Any]:
    cid = (content_id or "").strip()
    row = BANK_PRODUCT_CATALOG.get(cid)
    if not row:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content_id for bank transfer: {cid}",
        )
    return row


def _banking_configured() -> bool:
    return bool(BANK_IBAN and BANK_RECIPIENT and BANK_NAME)


def _generate_unique_transfer_code(conn, prefix: str) -> str:
    for _ in range(30):
        code = f"{prefix}-{random.randint(0, 9999):04d}"
        ex = conn.execute(
            sa_text("SELECT 1 FROM bank_transfer_requests WHERE transfer_code = :c LIMIT 1"),
            {"c": code},
        ).first()
        if not ex:
            return code
    raise HTTPException(status_code=500, detail="Could not allocate transfer code")


class PreviewBody(BaseModel):
    content_id: str = Field(..., min_length=3, max_length=120)


@router.post("/preview")
def bank_transfer_preview(body: PreviewBody):
    """IBAN + benzersiz açıklama kodu (henüz kayıt yok)."""
    if not _banking_configured():
        raise HTTPException(
            status_code=503,
            detail="Bank transfer is not configured (BANK_TRANSFER_* env)",
        )
    cat = _catalog_entry(body.content_id)
    prefix = str(cat["prefix"])
    with engine.connect() as conn:
        code = _generate_unique_transfer_code(conn, prefix)
    amount = cat["amount"]
    return {
        "transfer_code": code,
        "iban": BANK_IBAN,
        "recipient_name": BANK_RECIPIENT,
        "bank_name": BANK_NAME,
        "iban_label": BANK_IBAN_LABEL,
        "amount": float(amount),
        "product_name": cat["product_name"],
        "content_id": body.content_id.strip(),
        "instructions_tr": (
            "Lütfen havale/EFT açıklamasına yalnızca aşağıdaki kodu yazın. "
            "Tutarın tam olarak eşleşmesi gerekir."
        ),
    }


@router.post("/submit")
async def bank_transfer_submit(
    name: str = Form(...),
    email: str = Form(...),
    content_id: str = Form(...),
    transfer_code: str = Form(...),
    receipt: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not _banking_configured():
        raise HTTPException(status_code=503, detail="Bank transfer not configured")
    cat = _catalog_entry(content_id)
    code = (transfer_code or "").strip().upper()
    if not _TRANSFER_CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Invalid transfer code format")
    if not code.startswith(str(cat["prefix"]) + "-"):
        raise HTTPException(status_code=400, detail="Transfer code does not match product")

    raw = await receipt.read()
    if len(raw) > MAX_RECEIPT_BYTES:
        raise HTTPException(status_code=400, detail="Receipt file too large")
    ct = (receipt.content_type or "application/octet-stream").split(";")[0].strip()
    if ct not in ("image/jpeg", "image/png", "image/webp", "image/jpg"):
        raise HTTPException(status_code=400, detail="Receipt must be JPEG, PNG or WebP")
    b64 = base64.b64encode(raw).decode("ascii")
    data_url = f"data:{ct};base64,{b64}"

    nm = (name or "").strip()
    em = (email or "").strip().lower()
    if len(nm) < 2 or "@" not in em:
        raise HTTPException(status_code=400, detail="Invalid name or email")

    amount = cat["amount"]
    pname = str(cat["product_name"])
    try:
        if _is_pg():
            row = db.execute(
                sa_text("""
                INSERT INTO bank_transfer_requests (
                    name, email, product_name, content_id, amount, iban_label,
                    transfer_code, receipt_file_url, status
                ) VALUES (
                    :name, :email, :pname, :cid, :amount, :ilabel,
                    :tcode, :receipt, 'pending'
                )
                RETURNING id
            """),
                {
                    "name": nm,
                    "email": em,
                    "pname": pname,
                    "cid": content_id.strip(),
                    "amount": amount,
                    "ilabel": BANK_IBAN_LABEL,
                    "tcode": code,
                    "receipt": data_url,
                },
            ).first()
            rid = int(row[0]) if row else 0
        else:
            db.execute(
                sa_text("""
                INSERT INTO bank_transfer_requests (
                    name, email, product_name, content_id, amount, iban_label,
                    transfer_code, receipt_file_url, status
                ) VALUES (
                    :name, :email, :pname, :cid, :amount, :ilabel,
                    :tcode, :receipt, 'pending'
                )
            """),
                {
                    "name": nm,
                    "email": em,
                    "pname": pname,
                    "cid": content_id.strip(),
                    "amount": float(amount),
                    "ilabel": BANK_IBAN_LABEL,
                    "tcode": code,
                    "receipt": data_url,
                },
            )
            rid = int(db.execute(sa_text("SELECT last_insert_rowid()")).scalar() or 0)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate transfer code")
    logger.info("bank_transfer submitted id=%s code=%s email=%s", rid, code, em)
    return {
        "ok": True,
        "id": rid,
        "status": "pending",
        "message_tr": "Ödeme bildirimin alındı. Dekontun inceleniyor; onaylanınca e-posta adresine tanımlı erişim açılır.",
    }


@router.get("/status")
def bank_transfer_status(
    email: str = Query(...),
    transfer_code: str = Query(...),
    db: Session = Depends(get_db),
):
    em = (email or "").strip().lower()
    tc = (transfer_code or "").strip().upper()
    if "@" not in em or not tc:
        raise HTTPException(status_code=400, detail="Invalid query")
    row = db.execute(
        sa_text("""
        SELECT id, status, product_name, content_id, created_at
        FROM bank_transfer_requests
        WHERE LOWER(TRIM(email)) = :em AND UPPER(TRIM(transfer_code)) = :tc
        ORDER BY id DESC LIMIT 1
    """),
        {"em": em, "tc": tc},
    ).mappings().first()
    if not row:
        return {"found": False, "status": None}
    st = row["status"]
    msg = {
        "pending": "Bildirimin alındı. Havale dekontun kontrol ediliyor.",
        "approved": "Ödemen onaylandı. Erişimin açıldı — sayfayı yenileyebilirsin.",
        "rejected": "Bu başvuru reddedildi. Detay için destek ile iletişime geç.",
    }.get(st, st)
    return {
        "found": True,
        "status": st,
        "message_tr": msg,
        "product_name": row["product_name"],
        "content_id": row["content_id"],
    }


def _insert_shopier_unlock(
    db: Session,
    *,
    content_id: str,
    email: str,
    amount: float,
    product_name: str,
    transfer_code: str,
    request_id: int,
) -> None:
    oid = f"bank-hvl-{request_id}-{transfer_code}"
    meta = json.dumps(
        {"source": "bank_transfer", "transfer_code": transfer_code, "request_id": request_id},
        ensure_ascii=False,
    )
    rawp = json.dumps({"bank_transfer_request_id": request_id}, ensure_ascii=False)
    db.execute(
        sa_text("""
        INSERT INTO shopier_purchases (
            content_id, product_id, email, amount, currency, source,
            shopier_order_id, status, metadata_json,
            order_number, product_name, product_code, event_type, payment_status, raw_payload
        ) VALUES (
            :cid, :pid, :email, :amount, 'TRY', 'bank_transfer',
            :oid, 'completed', :meta,
            :tcode, :pname, NULL, 'bank_transfer.approved', 'paid', :rawp
        )
    """),
        {
            "cid": content_id,
            "pid": content_id,
            "email": email,
            "amount": amount,
            "oid": oid,
            "meta": meta,
            "tcode": transfer_code,
            "pname": (product_name or "")[:500],
            "rawp": rawp[:500000],
        },
    )


@admin_router.get("")
def admin_list_bank_transfers(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=200),
    _admin: dict = Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    q = "SELECT id, name, email, product_name, content_id, amount, iban_label, transfer_code, status, created_at FROM bank_transfer_requests WHERE 1=1"
    params: dict[str, Any] = {}
    if status in ("pending", "approved", "rejected"):
        q += " AND status = :st"
        params["st"] = status
    q += " ORDER BY id DESC LIMIT :lim"
    params["lim"] = limit
    rows = db.execute(sa_text(q), params).mappings().all()
    items = []
    for r in rows:
        d = dict(r)
        if d.get("amount") is not None:
            d["amount"] = float(d["amount"])
        items.append(d)
    return {"items": items}


@admin_router.get("/{request_id}")
def admin_get_bank_transfer(
    request_id: int,
    _admin: dict = Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    row = db.execute(
        sa_text("SELECT * FROM bank_transfer_requests WHERE id = :id"),
        {"id": request_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    d = dict(row)
    if d.get("amount") is not None:
        d["amount"] = float(d["amount"])
    return d


class RejectBody(BaseModel):
    note: Optional[str] = None


@admin_router.post("/{request_id}/approve")
def admin_approve_bank_transfer(
    request_id: int,
    _admin: dict = Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    lock_sql = (
        sa_text("SELECT * FROM bank_transfer_requests WHERE id = :id FOR UPDATE")
        if _is_pg()
        else sa_text("SELECT * FROM bank_transfer_requests WHERE id = :id")
    )
    row = db.execute(lock_sql, {"id": request_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Not pending: {row['status']}")

    try:
        _insert_shopier_unlock(
            db,
            content_id=str(row["content_id"]),
            email=str(row["email"]),
            amount=float(row["amount"]),
            product_name=str(row["product_name"]),
            transfer_code=str(row["transfer_code"]),
            request_id=request_id,
        )
        upd = (
            "UPDATE bank_transfer_requests SET status = 'approved', updated_at = NOW() WHERE id = :id"
            if _is_pg()
            else "UPDATE bank_transfer_requests SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = :id"
        )
        db.execute(sa_text(upd), {"id": request_id})
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.warning("approve bank transfer integrity: %s", e)
        raise HTTPException(status_code=409, detail="Unlock already exists or duplicate order id")

    logger.info("bank_transfer approved id=%s by admin=%s", request_id, _admin.get("email"))
    return {"ok": True, "status": "approved"}


@admin_router.post("/{request_id}/reject")
def admin_reject_bank_transfer(
    request_id: int,
    body: RejectBody = Body(default=RejectBody()),
    _admin: dict = Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    row = db.execute(
        sa_text("SELECT id, status FROM bank_transfer_requests WHERE id = :id"),
        {"id": request_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=400, detail="Not pending")
    note = (body.note or "").strip()[:2000]
    db.execute(
        sa_text("""
        UPDATE bank_transfer_requests
        SET status = 'rejected', admin_note = :note, updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
    """),
        {"id": request_id, "note": note or None},
    )
    db.commit()
    logger.info("bank_transfer rejected id=%s", request_id)
    return {"ok": True, "status": "rejected"}
