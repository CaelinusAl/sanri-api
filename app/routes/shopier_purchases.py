"""
Shopier ödemeleri — production: webhook + PAT ile API doğrulama.

- POST /shopier/webhook — imzalı bildirim, sipariş kaydı, gerekirse GET /orders/{id}
- GET /shopier/check/{content_id} — sunucu kaydı (device / email / JWT kullanıcı)
- POST /shopier/bind-device — e-posta + içerik → cihaz parmak izi
- GET /shopier/my-purchases — satın alımlar listesi

Tablo: shopier_purchases (satın alımlar; order_id = shopier_order_id unique)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError

from app.config.shopier_content_mapping import (
    product_id_to_content_id,
    resolve_content_id_from_title_and_product,
)
from app.db import get_db, engine
from app.services.shopier_rest import (
    get_shopier_order,
    list_shopier_webhooks,
    register_shopier_webhook,
)

logger = logging.getLogger("shopier")

router = APIRouter(prefix="/shopier", tags=["shopier"])

WEBHOOK_TOKEN = os.getenv("SHOPIER_WEBHOOK_TOKEN", "")
WEBHOOK_PLAIN_SECRET = os.getenv("SHOPIER_WEBHOOK_SECRET", "").strip()
ADMIN_SECRET = os.getenv("SANRI_ADMIN_SECRET", "sanri_admin_369")
SHOPIER_PAT = os.getenv("SHOPIER_PAT", "").strip()


def _default_shopier_webhook_url() -> str:
    """
    Tam callback URL: SHOPIER_WEBHOOK_CALLBACK_URL veya SANRI_API_PUBLIC_URL + /shopier/webhook
    """
    explicit = os.getenv("SHOPIER_WEBHOOK_CALLBACK_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    base = os.getenv("SANRI_API_PUBLIC_URL", "").strip().rstrip("/")
    if base:
        return f"{base}/shopier/webhook"
    return ""


def _verify_shopier_signature(payload: bytes, signature: str) -> bool:
    if not WEBHOOK_TOKEN or not signature:
        return False
    expected = hmac.new(WEBHOOK_TOKEN.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def _webhook_authorized(request: Request, raw_body: bytes) -> bool:
    if WEBHOOK_PLAIN_SECRET:
        got = request.headers.get("X-Sanri-Webhook-Secret", "").strip()
        if hmac.compare_digest(got, WEBHOOK_PLAIN_SECRET):
            return True
    if WEBHOOK_TOKEN:
        sig = (
            request.headers.get("Shopier-Signature", "")
            or request.headers.get("X-Shopier-Signature", "")
            or ""
        )
        if _verify_shopier_signature(raw_body, sig):
            return True
    return False


def _ensure_tables():
    is_pg = engine.dialect.name == "postgresql"
    with engine.connect() as conn:
        if is_pg:
            conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS shopier_purchases (
                    id SERIAL PRIMARY KEY,
                    content_id VARCHAR(120) NOT NULL,
                    product_id VARCHAR(120),
                    device_fp VARCHAR(64),
                    user_id INTEGER,
                    email VARCHAR(255),
                    amount NUMERIC(10,2),
                    currency VARCHAR(10) DEFAULT 'TRY',
                    source VARCHAR(40) DEFAULT 'webhook',
                    shopier_order_id VARCHAR(120),
                    status VARCHAR(40) DEFAULT 'completed',
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
        else:
            conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS shopier_purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id VARCHAR(120) NOT NULL,
                    product_id VARCHAR(120),
                    device_fp VARCHAR(64),
                    user_id INTEGER,
                    email VARCHAR(255),
                    amount REAL,
                    currency VARCHAR(10) DEFAULT 'TRY',
                    source VARCHAR(40) DEFAULT 'webhook',
                    shopier_order_id VARCHAR(120),
                    status VARCHAR(40) DEFAULT 'completed',
                    metadata_json TEXT,
                    order_number VARCHAR(120),
                    product_name VARCHAR(500),
                    product_code VARCHAR(120),
                    event_type VARCHAR(80),
                    payment_status VARCHAR(40),
                    raw_payload TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        if is_pg:
            for ddl in (
                "ALTER TABLE shopier_purchases ADD COLUMN IF NOT EXISTS order_number VARCHAR(120)",
                "ALTER TABLE shopier_purchases ADD COLUMN IF NOT EXISTS product_name VARCHAR(500)",
                "ALTER TABLE shopier_purchases ADD COLUMN IF NOT EXISTS product_code VARCHAR(120)",
                "ALTER TABLE shopier_purchases ADD COLUMN IF NOT EXISTS event_type VARCHAR(80)",
                "ALTER TABLE shopier_purchases ADD COLUMN IF NOT EXISTS payment_status VARCHAR(40)",
                "ALTER TABLE shopier_purchases ADD COLUMN IF NOT EXISTS raw_payload TEXT",
            ):
                try:
                    conn.execute(sa_text(ddl))
                except Exception:
                    logger.warning("shopier_purchases migration skip: %s", ddl[:72])
        else:
            for col, typ in (
                ("order_number", "VARCHAR(120)"),
                ("product_name", "VARCHAR(500)"),
                ("product_code", "VARCHAR(120)"),
                ("event_type", "VARCHAR(80)"),
                ("payment_status", "VARCHAR(40)"),
                ("raw_payload", "TEXT"),
            ):
                try:
                    conn.execute(
                        sa_text(f"ALTER TABLE shopier_purchases ADD COLUMN {col} {typ}")
                    )
                except Exception:
                    pass
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS ix_sp_device ON shopier_purchases (device_fp)
        """))
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS ix_sp_email ON shopier_purchases (email)
        """))
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS ix_sp_user ON shopier_purchases (user_id)
        """))
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS ix_sp_content ON shopier_purchases (content_id)
        """))
        try:
            if is_pg:
                conn.execute(sa_text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS ix_sp_order_id_unique
                    ON shopier_purchases (shopier_order_id)
                    WHERE shopier_order_id IS NOT NULL AND shopier_order_id <> ''
                """))
            else:
                conn.execute(sa_text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS ix_sp_order_id_unique
                    ON shopier_purchases (shopier_order_id)
                    WHERE shopier_order_id IS NOT NULL AND shopier_order_id != ''
                """))
        except Exception:
            logger.warning("ix_sp_order_id_unique oluşturulamadı")
        if is_pg:
            conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS email_leads (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    name VARCHAR(255),
                    source VARCHAR(60),
                    page VARCHAR(120),
                    ip_hash VARCHAR(64),
                    device_fp VARCHAR(64),
                    user_id INTEGER,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
        else:
            conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS email_leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email VARCHAR(255) NOT NULL,
                    name VARCHAR(255),
                    source VARCHAR(60),
                    page VARCHAR(120),
                    ip_hash VARCHAR(64),
                    device_fp VARCHAR(64),
                    user_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        conn.execute(sa_text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_el_email ON email_leads (email)
        """))
        conn.commit()


_ensure_tables()


def _sql_recent_purchase_window() -> str:
    if engine.dialect.name == "postgresql":
        return "created_at > NOW() - INTERVAL '45 days'"
    return "created_at > datetime('now', '-45 days')"


def _parse_amount(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _payment_is_paid(status: str) -> bool:
    """Shopier Order.paymentStatus: paid | unpaid (fulfillment ayrı alan)."""
    s = (status or "").lower().strip()
    return s in ("paid", "completed", "success", "1")


def _extract_line_item(order: dict) -> tuple[str, str, str]:
    items = order.get("lineItems") or order.get("items") or []
    if not items or not isinstance(items, list):
        return "", "", ""
    first = items[0] if isinstance(items[0], dict) else {}
    title = str(first.get("title") or "")
    pid = str(first.get("productId") or first.get("id") or "")
    code = str(first.get("productCode") or first.get("sku") or "")
    return title, pid, code


def _extract_totals(order: dict) -> tuple[float, str]:
    totals = order.get("totals")
    currency = str(order.get("currency") or "TRY")
    if isinstance(totals, dict):
        return _parse_amount(totals.get("total") or totals.get("amount")), currency
    if totals is not None:
        return _parse_amount(totals), currency
    return _parse_amount(order.get("total")), currency


def _merge_orders(base: dict, api: dict) -> dict:
    out = dict(base)
    for k, v in api.items():
        if v is not None and v != "" and v != []:
            out[k] = v
    return out


def _needs_api_enrichment(order: dict, preliminary_content: str) -> bool:
    oid = str(order.get("id") or order.get("orderId") or "").strip()
    if not oid or not SHOPIER_PAT:
        return False
    ps = str(order.get("paymentStatus") or order.get("status") or "").strip()
    if not ps:
        return True
    items = order.get("lineItems") or order.get("items")
    if items is None or items == []:
        return True
    if preliminary_content in ("", "unknown"):
        return True
    return False


async def _resolve_order_for_webhook(
    data: dict,
) -> tuple[dict, str, str]:
    """order dict, raw_payload string, event_type"""
    raw_str = json.dumps(data, ensure_ascii=False)
    event_type = str(data.get("event") or data.get("type") or "").strip()

    order = data.get("data")
    if not isinstance(order, dict):
        order = dict(data)

    title, pid, _code = _extract_line_item(order)
    pre_cid = product_id_to_content_id(pid)
    if not pre_cid:
        pre_cid = resolve_content_id_from_title_and_product(title, pid)

    oid = str(order.get("id") or order.get("orderId") or "").strip()
    if oid and SHOPIER_PAT and _needs_api_enrichment(order, pre_cid):
        api_order = await get_shopier_order(oid)
        if api_order:
            logger.info("Shopier webhook: enriched order via PAT id=%s", oid)
            order = _merge_orders(order, api_order)
        else:
            logger.warning("Shopier webhook: PAT enrichment failed id=%s", oid)

    return order, raw_str, event_type


def _order_payment_status(order: dict) -> str:
    return str(order.get("paymentStatus") or order.get("status") or "").strip()


# ═══════════════════════════════════════════════════════════════
# POST /shopier/webhook
# ═══════════════════════════════════════════════════════════════


@router.post("/webhook")
async def shopier_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    cli = request.client.host if request.client else ""
    logger.info(
        "Shopier webhook: POST /shopier/webhook len=%s client=%s",
        len(payload),
        cli,
    )

    if not _webhook_authorized(request, payload):
        logger.warning("Shopier webhook: unauthorized")
        raise HTTPException(status_code=401, detail="Webhook verification failed")

    try:
        data = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    order, raw_str, event_type = await _resolve_order_for_webhook(data)

    oid = str(order.get("id") or order.get("orderId") or "").strip()
    order_number = str(order.get("orderNumber") or order.get("number") or "").strip() or None
    pay_status = _order_payment_status(order)

    logger.info(
        "Shopier webhook event=%s order_id=%s paymentStatus=%s pat=%s",
        event_type or "(empty)",
        oid or "(missing)",
        pay_status or "(empty)",
        "yes" if SHOPIER_PAT else "no",
    )
    logger.debug("Shopier webhook payload_head=%s", raw_str[:3500])

    supported = (
        event_type in ("order.created", "order.paid", "payment.completed", "")
        or event_type.startswith("order.")
    )
    if not supported:
        return {"received": True, "action": "ignored_event", "event": event_type}

    if not _payment_is_paid(pay_status):
        logger.info("Shopier webhook: skipped unpaid order_id=%s status=%s", oid, pay_status)
        return {"received": True, "action": "skipped_unpaid"}

    if not oid:
        logger.warning("Shopier webhook: missing order id")
        return {"received": True, "action": "skipped_no_order_id"}

    title, raw_pid, product_code = _extract_line_item(order)
    amount, currency = _extract_totals(order)

    cid = product_id_to_content_id(raw_pid)
    if not cid:
        cid = resolve_content_id_from_title_and_product(title, raw_pid)
    if cid == "unknown":
        logger.warning(
            "Shopier webhook: unknown content product_id=%s title=%s",
            raw_pid,
            title[:80],
        )

    shipping = order.get("shippingInfo") or order.get("shipping") or {}
    email = ""
    if isinstance(shipping, dict):
        email = str(shipping.get("email") or "").strip()
    if not email:
        buyer = order.get("buyer") or order.get("customer") or {}
        if isinstance(buyer, dict):
            email = str(buyer.get("email") or "").strip()

    existing = db.execute(
        sa_text("SELECT id FROM shopier_purchases WHERE shopier_order_id = :oid"),
        {"oid": oid},
    ).first()

    if existing:
        logger.info("Shopier webhook: duplicate order_id=%s", oid)
        return {"received": True, "action": "duplicate"}

    meta = json.dumps(
        {"title": title, "event": event_type, "enriched": bool(SHOPIER_PAT)},
        ensure_ascii=False,
    )

    try:
        db.execute(
            sa_text("""
                INSERT INTO shopier_purchases (
                    content_id, product_id, email, amount, currency, source,
                    shopier_order_id, status, metadata_json,
                    order_number, product_name, product_code, event_type, payment_status, raw_payload
                ) VALUES (
                    :cid, :pid, :email, :amount, :currency, 'webhook',
                    :oid, 'completed', :meta,
                    :ordernum, :pname, :pcode, :ev, :pstat, :rawp
                )
            """),
            {
                "cid": cid,
                "pid": raw_pid or None,
                "email": email or None,
                "amount": amount,
                "currency": currency or "TRY",
                "oid": oid,
                "meta": meta,
                "ordernum": order_number,
                "pname": title[:500] if title else None,
                "pcode": product_code or None,
                "ev": event_type or None,
                "pstat": pay_status or None,
                "rawp": raw_str[:500000] if raw_str else None,
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("Shopier webhook: insert race duplicate order_id=%s", oid)
        return {"received": True, "action": "duplicate"}

    if email:
        try:
            db.execute(
                sa_text("""
                    INSERT INTO email_leads (email, source, page)
                    VALUES (:email, 'shopier_purchase', :content)
                    ON CONFLICT (email) DO NOTHING
                """),
                {"email": email.lower(), "content": cid},
            )
            db.commit()
        except Exception:
            db.rollback()

    return {"received": True, "action": "stored"}


class RegisterWebhookBody(BaseModel):
    """İsteğe bağlı: url yoksa SANRI_API_PUBLIC_URL veya SHOPIER_WEBHOOK_CALLBACK_URL kullanılır."""

    url: Optional[str] = None
    event: str = "order.created"
    list_after: bool = True


# ═══════════════════════════════════════════════════════════════
# POST /shopier/register-webhook — Shopier API ile webhook oluştur (PAT)
# GEÇİCİ: GET /shopier/register-webhook?secret=... — tarayıcı testi (sonra kaldır)
# ═══════════════════════════════════════════════════════════════


async def _shopier_register_webhook_core(
    body: RegisterWebhookBody,
    admin_credential: Optional[str],
) -> dict:
    """
    Shopier: POST https://api.shopier.com/v1/webhooks — Bearer SHOPIER_PAT
    Admin: POST’ta X-Admin-Secret; GEÇİCİ GET’te query ?secret=
    """
    if admin_credential != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Admin access denied")

    target = (body.url or "").strip() or _default_shopier_webhook_url()
    if not target:
        raise HTTPException(
            status_code=400,
            detail="Missing webhook URL: set body.url or SANRI_API_PUBLIC_URL / SHOPIER_WEBHOOK_CALLBACK_URL",
        )

    result = await register_shopier_webhook(url=target, event=body.event)

    err = result.get("error")
    if err == "pat_missing":
        raise HTTPException(status_code=503, detail=result.get("message", "SHOPIER_PAT missing"))
    if err == "invalid_url":
        raise HTTPException(status_code=400, detail=result.get("message", "Invalid URL"))
    if err == "invalid_event":
        raise HTTPException(status_code=400, detail=result.get("message", "Invalid event"))
    if err == "network_error":
        raise HTTPException(
            status_code=503,
            detail={"message": "Network error calling Shopier", "detail": result.get("message")},
        )
    if err == "token_error":
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Shopier rejected PAT (check SHOPIER_PAT)",
                "shopier_body": result.get("shopier_body"),
            },
        )
    if err == "duplicate_webhook":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Webhook likely already registered",
                "shopier_body": result.get("shopier_body"),
                "status_code": result.get("status_code"),
            },
        )
    if err == "shopier_error":
        raise HTTPException(
            status_code=502,
            detail={
                "message": result.get("message", "Shopier API error"),
                "status_code": result.get("status_code"),
                "shopier_body": result.get("shopier_body"),
            },
        )

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result)

    logger.info(
        "Shopier register-webhook: success event=%s url=%s token_hint=%s",
        body.event,
        target,
        result.get("token_hint"),
    )

    out: dict = {
        "message": "Webhook registered",
        "event": body.event,
        "url": target,
        "webhook": result.get("webhook"),
        "token_hint": result.get("token_hint"),
    }

    if body.list_after:
        listed, list_err = await list_shopier_webhooks(limit=50, page=1)
        out["webhooks_list_error"] = list_err
        out["webhooks"] = listed

    return out


@router.post("/register-webhook")
async def shopier_register_webhook_post(
    body: RegisterWebhookBody = Body(default_factory=RegisterWebhookBody),
    x_admin_secret: Optional[str] = Header(default=None),
):
    """Koruma: `X-Admin-Secret: SANRI_ADMIN_SECRET`"""
    return await _shopier_register_webhook_core(body, x_admin_secret)


@router.get("/register-webhook")
async def shopier_register_webhook_get(
    secret: str = Query(..., description="SANRI_ADMIN_SECRET — GEÇİCİ tarayıcı testi"),
    url: Optional[str] = Query(default=None),
    event: str = Query(default="order.created"),
    list_after: bool = Query(default=True),
):
    """
    GEÇİCİ — sadece test: tarayıcıdan açmak için.
    Örnek: /shopier/register-webhook?secret=...&event=order.created
    Üretimde kapat: bu route'u sil, yalnız POST kullan.
    """
    body = RegisterWebhookBody(url=url, event=event, list_after=list_after)
    return await _shopier_register_webhook_core(body, secret)


@router.get("/webhooks")
async def shopier_list_webhooks(
    limit: int = 50,
    page: int = 1,
    x_admin_secret: Optional[str] = Header(default=None),
):
    """Shopier GET /webhooks — kayıtlı abonelikleri listele (PAT)."""
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Admin access denied")
    items, err = await list_shopier_webhooks(limit=limit, page=page)
    if err:
        raise HTTPException(status_code=502, detail=err)
    return {"webhooks": items, "count": len(items)}


# ═══════════════════════════════════════════════════════════════
# POST /shopier/record — kapalı
# ═══════════════════════════════════════════════════════════════


@router.post("/record")
def record_purchase_disabled():
    raise HTTPException(
        status_code=403,
        detail="Client purchase recording is disabled. Purchases are verified via Shopier webhook only.",
    )


class BindDeviceBody(BaseModel):
    email: str
    content_id: str
    device_fp: str


@router.post("/bind-device")
def bind_purchase_to_device(body: BindDeviceBody, db: Session = Depends(get_db)):
    em = (body.email or "").strip().lower()
    cid = (body.content_id or "").strip()
    fp = (body.device_fp or "").strip()
    if not em or "@" not in em or not cid or not fp:
        raise HTTPException(status_code=400, detail="Invalid body")

    recent = _sql_recent_purchase_window()
    row = db.execute(
        sa_text(f"""
        SELECT id, device_fp FROM shopier_purchases
        WHERE content_id = :cid AND status = 'completed'
          AND LOWER(TRIM(email)) = :em
          AND {recent}
        ORDER BY created_at DESC
        LIMIT 1
    """),
        {"cid": cid, "em": em},
    ).first()

    if not row:
        return {"ok": False, "error": "not_found"}

    _id, existing_fp = row[0], (row[1] or "").strip()
    if existing_fp and existing_fp != fp:
        return {"ok": False, "error": "device_mismatch"}

    db.execute(
        sa_text("UPDATE shopier_purchases SET device_fp = :fp WHERE id = :id"),
        {"fp": fp, "id": _id},
    )
    db.commit()
    return {"ok": True}


def _row_unlock_for_content(
    db: Session, content_id: str, params: dict, or_clauses: list
) -> Any:
    if not or_clauses:
        return None
    where_or = "(" + " OR ".join(or_clauses) + ")"
    sql = f"""
        SELECT content_id, amount, currency, created_at
        FROM shopier_purchases
        WHERE content_id = :cid AND status = 'completed' AND {where_or}
        ORDER BY created_at DESC LIMIT 1
    """
    p = {"cid": content_id, **params}
    return db.execute(sa_text(sql), p).first()


def _auth_user_email(db: Session, authorization: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    if not authorization or not authorization.startswith("Bearer "):
        return None, None
    try:
        from app.services.auth import decode_token

        payload = decode_token(authorization.replace("Bearer ", "").strip())
        if not payload or not payload.get("sub"):
            return None, None
        user_id = int(payload["sub"])
        urow = db.execute(
            sa_text("SELECT email FROM users WHERE id = :id"),
            {"id": user_id},
        ).first()
        ue = str(urow[0]).strip().lower() if urow and urow[0] else None
        return user_id, ue if ue and "@" in ue else None
    except Exception:
        return None, None


@router.get("/check/{content_id}")
def check_purchase(
    content_id: str,
    device_fp: str = "",
    email: str = "",
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    cid = (content_id or "").strip()
    if not cid:
        return {"unlocked": False, "purchase": None}

    ors = []
    prm: dict = {}

    if device_fp:
        ors.append("device_fp = :fp")
        prm["fp"] = device_fp.strip()

    email_q = (email or "").strip().lower()
    if email_q and "@" in email_q:
        ors.append("LOWER(TRIM(email)) = :qemail")
        prm["qemail"] = email_q

    user_id, user_email = _auth_user_email(db, authorization)

    if user_id:
        ors.append("user_id = :uid")
        prm["uid"] = user_id
    if user_email:
        ors.append("LOWER(TRIM(email)) = :uemail")
        prm["uemail"] = user_email

    row = _row_unlock_for_content(db, cid, prm, ors)
    if not row:
        return {"unlocked": False, "purchase": None}

    content_id_r, amount, currency, created_at = row[0], row[1], row[2], row[3]
    purchased_at = str(created_at) if created_at else None
    amt = float(amount) if amount is not None else 0.0
    purchase = {
        "content_id": content_id_r,
        "amount": amt,
        "currency": str(currency or "TRY"),
        "purchased_at": purchased_at,
    }
    return {
        "unlocked": True,
        "purchase": purchase,
        "purchased_at": purchased_at,
    }


@router.get("/my-purchases")
def my_purchases(
    device_fp: str = "",
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    user_id, user_email = _auth_user_email(db, authorization)

    conditions = []
    params: dict = {}
    if device_fp:
        conditions.append("device_fp = :fp")
        params["fp"] = device_fp
    if user_id:
        conditions.append("user_id = :uid")
        params["uid"] = user_id
    if user_email:
        conditions.append("LOWER(TRIM(email)) = :uemail")
        params["uemail"] = user_email

    if not conditions:
        return {"purchases": []}

    where = " OR ".join(conditions)
    rows = db.execute(
        sa_text(f"""
        SELECT content_id, product_id, product_name, amount, currency,
               shopier_order_id, order_number, payment_status, created_at
        FROM shopier_purchases
        WHERE ({where}) AND status = 'completed'
        ORDER BY created_at DESC
    """),
        params,
    ).mappings().all()

    return {
        "purchases": [
            {
                "content_id": r["content_id"],
                "product_id": r["product_id"],
                "product_name": r["product_name"],
                "amount": float(r["amount"]) if r["amount"] else 0,
                "currency": r["currency"] or "TRY",
                "order_id": r["shopier_order_id"],
                "order_number": r["order_number"],
                "payment_status": r["payment_status"],
                "purchased_at": str(r["created_at"]) if r["created_at"] else None,
            }
            for r in rows
        ]
    }


class EmailLeadBody(BaseModel):
    email: str
    name: Optional[str] = None
    source: Optional[str] = "manual"
    page: Optional[str] = None
    device_fp: Optional[str] = None


@router.post("/collect-email")
def collect_email(
    body: EmailLeadBody,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not body.email or "@" not in body.email:
        raise HTTPException(status_code=400, detail="Invalid email")

    user_id = None
    if authorization and authorization.startswith("Bearer "):
        try:
            from app.services.auth import decode_token

            payload = decode_token(authorization.replace("Bearer ", "").strip())
            if payload and payload.get("sub"):
                user_id = int(payload["sub"])
        except Exception:
            pass

    ip_raw = request.headers.get("x-forwarded-for", request.client.host or "")
    ip_hash = hashlib.sha256(ip_raw.encode()).hexdigest()[:16]

    db.execute(
        sa_text("""
        INSERT INTO email_leads (email, name, source, page, ip_hash, device_fp, user_id)
        VALUES (:email, :name, :source, :page, :ip, :fp, :uid)
        ON CONFLICT (email) DO UPDATE SET
            name = COALESCE(EXCLUDED.name, email_leads.name),
            source = EXCLUDED.source,
            page = EXCLUDED.page
    """),
        {
            "email": body.email.strip().lower(),
            "name": body.name,
            "source": body.source,
            "page": body.page,
            "ip": ip_hash,
            "fp": body.device_fp,
            "uid": user_id,
        },
    )
    db.commit()
    return {"ok": True}


@router.get("/admin/purchases")
def admin_purchases(
    x_admin_secret: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Admin access denied")

    rows = db.execute(
        sa_text("""
        SELECT id, content_id, product_id, product_name, device_fp, user_id, email,
               amount, currency, source, shopier_order_id, order_number,
               status, payment_status, event_type, created_at
        FROM shopier_purchases ORDER BY created_at DESC LIMIT 100
    """)
    ).mappings().all()

    total = db.execute(
        sa_text("SELECT COALESCE(SUM(amount), 0) FROM shopier_purchases WHERE status = 'completed'")
    ).scalar()

    leads = db.execute(sa_text("SELECT COUNT(*) FROM email_leads")).scalar()

    return {
        "total_revenue": float(total),
        "total_purchases": len(rows),
        "total_email_leads": leads,
        "purchases": [dict(r) for r in rows],
    }
