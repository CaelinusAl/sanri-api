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
# Alternatif isimler: BANK_TRANSFER_BANK / BANK_TRANSFER_NAME (alıcı) — panel uyumu


def _env_any(*keys: str) -> str:
    for k in keys:
        v = os.getenv(k, "").strip()
        if v:
            return v
    return ""


def load_banking_from_env() -> dict[str, str]:
    """
    Her istekte os.environ'dan oku (import anındaki değerler worker'da eski kalmasın).
    Okunan isimler (sırayla ilk dolu olan):
    - IBAN: BANK_TRANSFER_IBAN | BANK_IBAN
    - Alıcı: BANK_TRANSFER_RECIPIENT_NAME | BANK_TRANSFER_NAME | BANK_ACCOUNT_NAME | BANK_ACCOUND_NAME (typo)
    - Banka: BANK_TRANSFER_BANK_NAME | BANK_TRANSFER_BANK | BANK_NAME
    - Etiket: BANK_TRANSFER_IBAN_LABEL (yoksa SANRI — TRY)
    - Not: BANK_TRANSFER_NOTE
    """
    return {
        "iban": _env_any("BANK_TRANSFER_IBAN", "BANK_IBAN"),
        "recipient": _env_any(
            "BANK_TRANSFER_RECIPIENT_NAME",
            "BANK_TRANSFER_NAME",
            "BANK_ACCOUNT_NAME",
            "BANK_ACCOUND_NAME",  # yaygın yazım hatası (ACCOUND)
        ),
        "bank_name": _env_any(
            "BANK_TRANSFER_BANK_NAME", "BANK_TRANSFER_BANK", "BANK_NAME"
        ),
        "iban_label": _env_any("BANK_TRANSFER_IBAN_LABEL") or "SANRI — TRY",
        "note": _env_any("BANK_TRANSFER_NOTE"),
    }


def _banking_ok(b: dict[str, str]) -> bool:
    return bool(b.get("iban") and b.get("recipient") and b.get("bank_name"))


def _mask_iban_for_log(iban: str) -> str:
    s = re.sub(r"\s+", "", (iban or "").strip())
    if not s:
        return "(boş)"
    if len(s) < 10:
        return s[:4] + "…"
    return s[:6] + "…" + s[-4:]


def _log_bank_transfer_env_diag(where: str, content_id: str, b: dict[str, str]) -> None:
    """Tam IBAN/log sızmaz; hangi env anahtarlarının dolu olduğu + çözümlenmiş uzunluklar."""
    tracked = (
        "BANK_TRANSFER_IBAN",
        "BANK_IBAN",
        "BANK_TRANSFER_RECIPIENT_NAME",
        "BANK_TRANSFER_NAME",
        "BANK_ACCOUNT_NAME",
        "BANK_ACCOUND_NAME",
        "BANK_TRANSFER_BANK_NAME",
        "BANK_TRANSFER_BANK",
        "BANK_NAME",
        "BANK_TRANSFER_IBAN_LABEL",
        "BANK_TRANSFER_NOTE",
    )
    present = {k: bool(os.getenv(k, "").strip()) for k in tracked}
    logger.info(
        "%s | content_id=%s | db_dialect=%s | env_keys_present=%s | "
        "resolved_lens iban=%s recipient=%s bank=%s | iban_mask=%s",
        where,
        content_id,
        engine.dialect.name,
        present,
        len(b.get("iban") or ""),
        len(b.get("recipient") or ""),
        len(b.get("bank_name") or ""),
        _mask_iban_for_log(b.get("iban") or ""),
    )

_DEFAULT_INSTRUCTIONS_TR = (
    "Lütfen havale/EFT açıklamasına yalnızca aşağıdaki kodu yazın. "
    "Tutarın tam olarak eşleşmesi gerekir."
)

MAX_RECEIPT_BYTES = int(os.getenv("BANK_TRANSFER_MAX_RECEIPT_BYTES", str(1_500_000)))

# ── Havale / EFT ürün kataloğu (TEK KAYNAK) ─────────────────────────
# Desteklenen tüm content_id değerleri = bu sözlüğün anahtarları.
# Alanlar: prefix (havale açıklama kodu öneği, A-Z0-9), amount, product_name;
# isteğe bağlı iban_label → doluysa önizleme / kayıtta global env etiketinin üstüne yazar.
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
    "okuma_23": {
        "prefix": "OKUMA",
        "amount": Decimal("9.90"),
        "product_name": "Okuma — Jap_On_ya +81 derin açılım",
        "iban_label": "SANRI Okuma devamı — 9,90 TL — TRY",
    },
}

_TRANSFER_CODE_RE = re.compile(r"^[A-Z0-9]+-\d{4}$")


def supported_bank_transfer_content_ids() -> list[str]:
    """Desteklenen content_id listesi — yalnızca BANK_PRODUCT_CATALOG anahtarları."""
    return list(BANK_PRODUCT_CATALOG.keys())


def _effective_iban_label(cat: dict[str, Any], banking: dict[str, str]) -> str:
    """Ürün bazlı iban_label varsa onu kullan; yoksa env’den gelen varsayılan."""
    custom = (cat.get("iban_label") or "").strip()
    if custom:
        return custom
    return (banking.get("iban_label") or "").strip() or "SANRI — TRY"


def _is_pg() -> bool:
    return engine.dialect.name == "postgresql"


def _ensure_bank_transfer_table() -> None:
    """CREATE TABLE + index — SQLAlchemy 2: begin() ile commit garantisi (connect()+commit bazen f405/rollback)."""
    with engine.begin() as conn:
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


try:
    _ensure_bank_transfer_table()
except Exception as e:
    logger.exception("bank_transfer table migration (ilk açılış): %s", e)


def _catalog_entry(content_id: str) -> dict[str, Any]:
    cid = (content_id or "").strip()
    row = BANK_PRODUCT_CATALOG.get(cid)
    if not row:
        supported = supported_bank_transfer_content_ids()
        logger.warning(
            "bank_transfer unsupported content_id=%r supported=%s",
            cid,
            supported,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_content_id",
                "message": f"Bu içerik için havale / EFT tanımlı değil: {cid!r}",
                "received_content_id": cid,
                "supported_content_ids": supported,
            },
        )
    return row


def _banking_env_missing_detail(cid: str, b: dict[str, str]) -> dict[str, Any]:
    missing = []
    if not b.get("iban"):
        missing.append("BANK_TRANSFER_IBAN veya BANK_IBAN")
    if not b.get("recipient"):
        missing.append(
            "BANK_TRANSFER_RECIPIENT_NAME / BANK_TRANSFER_NAME / BANK_ACCOUNT_NAME "
            "(veya BANK_ACCOUND_NAME)"
        )
    if not b.get("bank_name"):
        missing.append("BANK_TRANSFER_BANK_NAME / BANK_TRANSFER_BANK / BANK_NAME")
    return {
        "error": "bank_transfer_env_missing",
        "message": "Havale / EFT için banka bilgisi eksik (API ortam değişkenleri).",
        "received_content_id": cid,
        "supported_content_ids": supported_bank_transfer_content_ids(),
        "missing_env_variables": missing,
    }


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


# Repoda sabit — canlıda farklıysa Railway eski imaj/deploy kullanıyordur.
BANK_TRANSFER_ROUTER_BUILD_ID = "sanri-api-bank-transfer-2026-04-02"


@router.get("/ready")
def bank_transfer_ready():
    """
    Deploy doğrulama + (gizli veri sızdırmadan) env çözümleme özeti.
    Eski API’lerde bu route yok → 404 = hâlâ güncel kod yok.
    """
    b = load_banking_from_env()
    return {
        "build_id": BANK_TRANSFER_ROUTER_BUILD_ID,
        "banking_complete": _banking_ok(b),
        "resolved": {
            "iban": bool(b.get("iban")),
            "recipient": bool(b.get("recipient")),
            "bank_name": bool(b.get("bank_name")),
        },
    }


@router.post("/preview")
def bank_transfer_preview(body: PreviewBody):
    """IBAN + benzersiz açıklama kodu (henüz kayıt yok)."""
    cid = body.content_id.strip()
    logger.info(
        "POST /bank-transfer/preview | incoming content_id=%r | len=%s | in_catalog=%s",
        cid,
        len(cid),
        cid in BANK_PRODUCT_CATALOG,
    )

    # 1) Katalog (desteklenmeyen → 400, net gövde)
    cat = _catalog_entry(cid)

    b = load_banking_from_env()
    _log_bank_transfer_env_diag("POST /bank-transfer/preview", cid, b)
    if not _banking_ok(b):
        raise HTTPException(
            status_code=400,
            detail=_banking_env_missing_detail(cid, b),
        )
    try:
        _ensure_bank_transfer_table()
    except Exception as e:
        logger.exception("bank_transfer ensure before preview")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "bank_transfer_schema_error",
                "message": str(e),
                "received_content_id": cid,
                "supported_content_ids": supported_bank_transfer_content_ids(),
            },
        ) from e
    prefix = str(cat["prefix"])
    with engine.connect() as conn:
        code = _generate_unique_transfer_code(conn, prefix)
    amount = cat["amount"]
    return {
        "transfer_code": code,
        "iban": b["iban"],
        "recipient_name": b["recipient"],
        "bank_name": b["bank_name"],
        "iban_label": _effective_iban_label(cat, b),
        "amount": float(amount),
        "product_name": cat["product_name"],
        "content_id": cid,
        "instructions_tr": b["note"] or _DEFAULT_INSTRUCTIONS_TR,
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
    scid = (content_id or "").strip()
    logger.info(
        "POST /bank-transfer/submit | incoming content_id=%r | in_catalog=%s",
        scid,
        scid in BANK_PRODUCT_CATALOG,
    )
    cat = _catalog_entry(scid)
    b_submit = load_banking_from_env()
    _log_bank_transfer_env_diag("POST /bank-transfer/submit", scid, b_submit)
    if not _banking_ok(b_submit):
        raise HTTPException(
            status_code=400,
            detail=_banking_env_missing_detail(scid, b_submit),
        )
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
    ilabel = _effective_iban_label(cat, b_submit)
    try:
        if _is_pg():
            rid = int(
                db.execute(
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
                        "cid": scid,
                        "amount": amount,
                        "ilabel": ilabel,
                        "tcode": code,
                        "receipt": data_url,
                    },
                ).scalar_one()
            )
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
                    "cid": scid,
                    "amount": float(amount),
                    "ilabel": ilabel,
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
