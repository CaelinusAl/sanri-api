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
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from app.routes.bank_transfer_helpers import (
    build_epc_style_qr_payload,
    ensure_bank_transfer_aux_tables,
    qrcode_png_base64,
    start_bank_transfer_sweep_scheduler,
    sweep_expired_temp_unlocks,
)

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db, engine
from app.validation.contact_email import normalize_contact_email
from app.routes.admin import _require_jwt
from app.services.email_service import send_admin_bank_transfer_notification

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
    "Açıklama kodunu EFT/havale açıklamasına aynen yazın (ek kelime olmadan). "
    "Tutarın tam olarak eşleşmesi gerekir. Ödeme manuel kontrol edilir."
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
    ensure_bank_transfer_aux_tables()
except Exception as e:
    logger.exception("bank_transfer table migration (ilk açılış): %s", e)

_bank_sweep_armed = False


def _arm_bank_temp_sweep() -> None:
    global _bank_sweep_armed
    if _bank_sweep_armed:
        return
    _bank_sweep_armed = True
    start_bank_transfer_sweep_scheduler()


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
    _arm_bank_temp_sweep()
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
    qr_payload = build_epc_style_qr_payload(
        b["iban"],
        b["recipient"],
        amount,
        code,
    )
    try:
        qr_b64 = qrcode_png_base64(qr_payload)
    except Exception as e:
        logger.warning("bank_transfer QR generate failed: %s", e)
        qr_b64 = ""
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
        "fast_qr_payload": qr_payload,
        "qr_png_base64": qr_b64,
        "qr_hint_tr": (
            "Banka uygulamanızdan QR ile ödeme açmayı deneyin; "
            "açıklamaya yine aynı kodu yazmanız gerekir."
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
    try:
        em = normalize_contact_email(email)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_email",
                "message_tr": "Geçerli bir e-posta adresi zorunludur.",
            },
        )
    if len(nm) < 2:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_name", "message_tr": "Ad soyad en az 2 karakter olmalıdır."},
        )

    dup = db.execute(
        sa_text(
            "SELECT id, status FROM bank_transfer_requests "
            "WHERE UPPER(TRIM(transfer_code)) = :tc LIMIT 1"
        ),
        {"tc": code},
    ).mappings().first()
    if dup:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate_transfer_code",
                "message_tr": (
                    "Bu açıklama kodu ile zaten bir bildirim kayıtlı. "
                    "Yeni ödeme için havale sayfasına dönüp yeni kod üretin; "
                    "aynı kodu iki kez kullanamazsınız."
                ),
                "existing_status": str(dup["status"]),
            },
        )

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
        try:
            send_admin_bank_transfer_notification(
                request_id=rid,
                customer_name=nm,
                customer_email=em,
                product_name=pname,
                content_id=scid,
                amount=amount,
                transfer_code=code,
            )
        except Exception as mail_exc:
            logger.warning("Bank transfer admin notify email failed: %s", mail_exc)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate_transfer_code",
                "message_tr": (
                    "Bu açıklama kodu ile kayıt oluşturulamadı (çakışma). "
                    "Sayfayı yenileyip yeni kod alın veya destek ile iletişime geçin."
                ),
            },
        )
    logger.info(
        "contact_email_audit received_email=%r stored_email=%r source_flow=%s request_id=%s transfer_code=%s",
        (email or "").strip()[:320],
        em,
        "bank_transfer_submit",
        rid,
        code,
    )
    return {
        "ok": True,
        "id": rid,
        "status": "pending",
        "message_tr": (
            "Ödeme bildirimin alındı. Kontrol sonrası erişimin açılacak."
        ),
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
        "pending": "Bildirimin alındı. Ödeme manuel kontrol ediliyor; dekont ve tutar onaylanınca erişim açılır.",
        "approved": "Ödemen onaylandı. Erişimin açıldı — ilgili sayfayı yenileyebilirsin.",
        "rejected": "Bu başvuru reddedildi. Detay için destek ile iletişime geç.",
    }.get(st, st)
    return {
        "found": True,
        "status": st,
        "message_tr": msg,
        "product_name": row["product_name"],
        "content_id": row["content_id"],
    }


BENIM_ALANIM_AFTER_VERIFY_TR = (
    "Ders ve müfredat ilerlemen Benim Alanım’da: /benim-alanim — "
    "Öğrendiklerim, Kod haritam ve Satın aldıklarım bölümlerinden takip edebilirsin."
)
BENIM_ALANIM_AFTER_VERIFY_EN = (
    "Track your lessons in My Space at /benim-alanim — My Learnings, My Code Map, and My Purchases."
)


class VerifyBody(BaseModel):
    transfer_code: str = Field(..., min_length=6, max_length=32)
    amount: Any  # float | str — Decimal’a çevrilir
    email: EmailStr
    device_fp: Optional[str] = Field(default=None, max_length=80)


@router.post("/verify")
def bank_transfer_verify(body: VerifyBody, db: Session = Depends(get_db)):
    """
    Hızlı doğrulama: son 10 dk içinde gelen ödeme sinyali (amount + transfer_code) varsa
    kalıcı onay + unlock. Yoksa (pending talep eşleşiyorsa) 15 dk geçici erişim.
    """
    _arm_bank_temp_sweep()
    sweep_expired_temp_unlocks()
    ensure_bank_transfer_aux_tables()

    code = (body.transfer_code or "").strip().upper()
    try:
        email = normalize_contact_email(str(body.email))
    except ValueError:
        _log_verify_attempt_isolated(code, 0.0, str(body.email), None, False, "invalid_email")
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_email", "message_tr": "Geçerli bir e-posta gerekli."},
        )
    fp = (body.device_fp or "").strip() or None
    try:
        amt = Decimal(str(body.amount)).quantize(Decimal("0.01"))
    except Exception:
        _log_verify_attempt_isolated(code, 0.0, email, fp, False, "invalid_amount")
        raise HTTPException(status_code=400, detail="Invalid amount")

    if not _TRANSFER_CODE_RE.match(code):
        _log_verify_attempt_isolated(code, float(amt), email, fp, False, "invalid_transfer_code")
        raise HTTPException(status_code=400, detail="Invalid transfer_code")

    row = db.execute(
        sa_text("""
        SELECT * FROM bank_transfer_requests
        WHERE UPPER(TRIM(transfer_code)) = :tc AND status = 'pending'
        ORDER BY id DESC LIMIT 1
    """),
        {"tc": code},
    ).mappings().first()

    if not row:
        _log_verify_attempt_isolated(code, float(amt), email, fp, False, "no_pending_request")
        return {
            "ok": False,
            "matched": False,
            "approved": False,
            "outcome": "no_pending_request",
            "message_tr": "Bu kod veya e-posta ile bekleyen havale talebi bulunamadı. Önce dekont bildirimini gönder veya bilgileri kontrol et.",
        }

    try:
        r_amt = Decimal(str(row["amount"])).quantize(Decimal("0.01"))
    except Exception:
        r_amt = Decimal("0")
    if r_amt != amt:
        _log_verify_attempt_isolated(code, float(amt), email, fp, False, "amount_mismatch")
        return {
            "ok": False,
            "matched": False,
            "approved": False,
            "outcome": "amount_mismatch",
            "message_tr": "Tutar, talepteki tutar ile eşleşmiyor.",
        }

    if str(row["email"]).strip().lower() != email:
        _log_verify_attempt_isolated(code, float(amt), email, fp, False, "email_mismatch")
        raise HTTPException(
            status_code=403,
            detail="E-posta bu havale talebiyle eşleşmiyor.",
        )

    if _is_pg():
        inc = db.execute(
            sa_text("""
            SELECT id FROM bank_transfer_incoming_events
            WHERE UPPER(TRIM(transfer_code)) = :tc
              AND amount = :amt
              AND detected_at > NOW() - INTERVAL '10 minutes'
            ORDER BY id DESC LIMIT 1
        """),
            {"tc": code, "amt": amt},
        ).first()
    else:
        inc = db.execute(
            sa_text("""
            SELECT id FROM bank_transfer_incoming_events
            WHERE UPPER(TRIM(transfer_code)) = :tc
              AND ABS(amount - :amtf) < 0.02
              AND datetime(detected_at) > datetime('now', '-600 seconds')
            ORDER BY id DESC LIMIT 1
        """),
            {"tc": code, "amtf": float(amt)},
        ).first()

    if inc:
        approve_bank_transfer_request_core(db, int(row["id"]))
        logger.info(
            "bank_transfer verify AUTO-APPROVED request_id=%s code=%s (incoming match)",
            row["id"],
            code,
        )
        _log_verify_attempt_isolated(code, float(amt), email, fp, True, "matched_incoming")
        return {
            "ok": True,
            "matched": True,
            "approved": True,
            "outcome": "matched_incoming",
            "message_tr": "Ödemen banka sinyaliyle eşleşti; erişimin kalıcı olarak açıldı.",
            "benim_alanim_message_tr": BENIM_ALANIM_AFTER_VERIFY_TR,
            "benim_alanim_message_en": BENIM_ALANIM_AFTER_VERIFY_EN,
            "content_id": str(row["content_id"]),
        }

    exp = _grant_temp_unlock_15m(
        db,
        request_id=int(row["id"]),
        email=email,
        content_id=str(row["content_id"]),
        transfer_code=code,
        device_fp=fp,
    )
    _log_verify_attempt_isolated(code, float(amt), email, fp, False, "temp_unlock_15m")
    logger.info(
        "bank_transfer verify TEMP unlock request_id=%s code=%s until=%s",
        row["id"],
        code,
        exp,
    )
    return {
        "ok": True,
        "matched": False,
        "approved": False,
        "temp_unlock": True,
        "outcome": "temp_unlock_15m",
        "temp_expires_at": exp.isoformat() if hasattr(exp, "isoformat") else str(exp),
        "temp_expires_in_seconds": 900,
        "message_tr": (
            "Son 10 dakikada banka tarafı sinyali bulunamadı; 15 dakikalığına geçici erişim verildi. "
            "Süre dolmadan ödeme onaylanmazsa erişim kapanır — dekont yükle veya bir süre sonra tekrar dene."
        ),
        "benim_alanim_message_tr": (
            "Geçici erişimle derse devam edebilirsin; kalıcı onay sonrası ilerlemen yine Benim Alanım’dan "
            "(Öğrendiklerim, Satın aldıklarım) takip edilir."
        ),
        "benim_alanim_message_en": (
            "Temporary access is active; after final approval, track progress in My Space (My Learnings, My Purchases)."
        ),
        "content_id": str(row["content_id"]),
    }


def _log_verify_attempt_isolated(
    transfer_code: str,
    amount: float,
    email: Optional[str],
    device_fp: Optional[str],
    matched: bool,
    outcome: str,
) -> None:
    try:
        ensure_bank_transfer_aux_tables()
        matched_b = matched if _is_pg() else (1 if matched else 0)
        with engine.begin() as conn:
            if _is_pg():
                conn.execute(
                    sa_text("""
                    INSERT INTO bank_transfer_verify_attempts
                    (transfer_code, amount, email, device_fp, matched, outcome)
                    VALUES (:tc, :amt, :em, :fp, :matched, :outcome)
                """),
                    {
                        "tc": transfer_code,
                        "amt": amount,
                        "em": email,
                        "fp": device_fp,
                        "matched": matched,
                        "outcome": outcome[:48],
                    },
                )
            else:
                conn.execute(
                    sa_text("""
                    INSERT INTO bank_transfer_verify_attempts
                    (transfer_code, amount, email, device_fp, matched, outcome)
                    VALUES (:tc, :amt, :em, :fp, :matched, :outcome)
                """),
                    {
                        "tc": transfer_code,
                        "amt": amount,
                        "em": email,
                        "fp": device_fp,
                        "matched": matched_b,
                        "outcome": outcome[:48],
                    },
                )
    except Exception as e:
        logger.warning("verify_attempt log failed: %s", e)


def _revoke_temp_unlocks_for_request_db(db: Session, request_id: int) -> None:
    if _is_pg():
        db.execute(
            sa_text(
                "UPDATE bank_transfer_temp_unlocks SET revoked = true "
                "WHERE request_id = :rid AND revoked = false"
            ),
            {"rid": request_id},
        )
    else:
        db.execute(
            sa_text(
                "UPDATE bank_transfer_temp_unlocks SET revoked = 1 "
                "WHERE request_id = :rid AND revoked = 0"
            ),
            {"rid": request_id},
        )


def approve_bank_transfer_request_core(db: Session, request_id: int) -> dict[str, Any]:
    """pending talebi shopier_purchases + approved yapar (admin onayı veya otomatik verify)."""
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

    _revoke_temp_unlocks_for_request_db(db, request_id)
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
        raise HTTPException(
            status_code=409, detail="Unlock already exists or duplicate order id"
        ) from e

    return {"ok": True, "status": "approved", "request_id": request_id}


def _grant_temp_unlock_15m(
    db: Session,
    *,
    request_id: int,
    email: str,
    content_id: str,
    transfer_code: str,
    device_fp: Optional[str],
) -> datetime:
    _revoke_temp_unlocks_for_request_db(db, request_id)
    if _is_pg():
        row = db.execute(
            sa_text("""
            INSERT INTO bank_transfer_temp_unlocks
            (request_id, email, content_id, transfer_code, device_fp, expires_at)
            VALUES (:rid, :em, :cid, :tc, :fp, NOW() + INTERVAL '15 minutes')
            RETURNING expires_at
        """),
            {
                "rid": request_id,
                "em": email,
                "cid": content_id,
                "tc": transfer_code,
                "fp": device_fp,
            },
        ).first()
        exp = row[0] if row else None
    else:
        db.execute(
            sa_text("""
            INSERT INTO bank_transfer_temp_unlocks
            (request_id, email, content_id, transfer_code, device_fp, expires_at)
            VALUES (:rid, :em, :cid, :tc, :fp, datetime('now', '+15 minutes'))
        """),
            {
                "rid": request_id,
                "em": email,
                "cid": content_id,
                "tc": transfer_code,
                "fp": device_fp,
            },
        )
        exp = db.execute(
            sa_text("SELECT expires_at FROM bank_transfer_temp_unlocks WHERE id = last_insert_rowid()")
        ).scalar()
    db.commit()
    if isinstance(exp, datetime):
        return exp
    return datetime.now(timezone.utc) + timedelta(minutes=15)


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


class IncomingBankSignalBody(BaseModel):
    transfer_code: str = Field(..., min_length=6, max_length=32)
    amount: Any
    meta: Optional[Dict[str, Any]] = None


@admin_router.post("/incoming-signal")
def admin_record_bank_incoming_signal(
    body: IncomingBankSignalBody,
    _admin: dict = Depends(_require_jwt),
    db: Session = Depends(get_db),
):
    """
    Banka / entegrasyondan gelen tutar + açıklama kodu kaydı.
    Kullanıcı POST /bank-transfer/verify ile eşleştirirse son 10 dk içindeki kayıt onay tetikler.
    """
    ensure_bank_transfer_aux_tables()
    code = (body.transfer_code or "").strip().upper()
    if not _TRANSFER_CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Invalid transfer_code")
    try:
        amt = Decimal(str(body.amount)).quantize(Decimal("0.01"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid amount")
    meta_s = json.dumps(body.meta or {}, ensure_ascii=False)
    if _is_pg():
        db.execute(
            sa_text("""
                INSERT INTO bank_transfer_incoming_events (amount, transfer_code, meta)
                VALUES (:amt, :tc, CAST(:meta AS jsonb))
            """),
            {"amt": amt, "tc": code, "meta": meta_s},
        )
    else:
        db.execute(
            sa_text("""
                INSERT INTO bank_transfer_incoming_events (amount, transfer_code, meta)
                VALUES (:amt, :tc, :meta)
            """),
            {"amt": float(amt), "tc": code, "meta": meta_s},
        )
    db.commit()
    logger.info(
        "bank_transfer incoming_signal code=%s amount=%s admin=%s",
        code,
        amt,
        _admin.get("email"),
    )
    return {"ok": True, "transfer_code": code, "amount": float(amt)}


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
    ensure_bank_transfer_aux_tables()
    out = approve_bank_transfer_request_core(db, request_id)
    logger.info("bank_transfer approved id=%s by admin=%s", request_id, _admin.get("email"))
    return out


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
