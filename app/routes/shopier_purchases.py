"""
Shopier purchase tracking — server-side persistence.

Supports three unlock verification methods:
  1. Shopier webhook (order.created) — most reliable
  2. Frontend-recorded purchase (OdemeBasarili page) — fallback
  3. Device fingerprint matching — works for anonymous users

Tables: shopier_purchases, email_leads
"""

import os
import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.db import get_db, engine

logger = logging.getLogger("shopier")

router = APIRouter(prefix="/shopier", tags=["shopier"])

WEBHOOK_TOKEN = os.getenv("SHOPIER_WEBHOOK_TOKEN", "")
ADMIN_SECRET = os.getenv("SANRI_ADMIN_SECRET", "sanri_admin_369")


def _ensure_tables():
    with engine.connect() as conn:
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
                source VARCHAR(20) DEFAULT 'frontend',
                shopier_order_id VARCHAR(120),
                status VARCHAR(20) DEFAULT 'completed',
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
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
        conn.execute(sa_text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_el_email ON email_leads (email)
        """))
        conn.commit()


_ensure_tables()


def _verify_shopier_signature(payload: bytes, signature: str) -> bool:
    if not WEBHOOK_TOKEN:
        return False
    expected = hmac.new(
        WEBHOOK_TOKEN.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ═══════════════════════════════════════════════════════════════
# POST /shopier/webhook — Shopier order.created webhook
# ═══════════════════════════════════════════════════════════════

@router.post("/webhook")
async def shopier_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("Shopier-Signature", "")

    if WEBHOOK_TOKEN and not _verify_shopier_signature(payload, signature):
        logger.warning("Shopier webhook: invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        data = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = data.get("event", "")
    order = data.get("data", data)

    logger.info(f"Shopier webhook: {event_type}")

    if event_type in ("order.created", ""):
        order_id = str(order.get("id", ""))
        payment_status = order.get("paymentStatus", "paid")

        if payment_status != "paid":
            return {"received": True, "action": "skipped_unpaid"}

        email = ""
        shipping = order.get("shippingInfo", {})
        if shipping:
            email = shipping.get("email", "")

        totals = order.get("totals", {})
        amount = float(totals.get("total", 0)) if totals else 0

        line_items = order.get("lineItems", [])
        product_title = line_items[0].get("title", "") if line_items else ""
        product_id = line_items[0].get("productId", "") if line_items else ""

        content_id = _resolve_content_id(product_title, product_id)

        existing = db.execute(sa_text(
            "SELECT id FROM shopier_purchases WHERE shopier_order_id = :oid"
        ), {"oid": order_id}).first()

        if not existing:
            db.execute(sa_text("""
                INSERT INTO shopier_purchases
                    (content_id, product_id, email, amount, currency, source, shopier_order_id, status, metadata_json)
                VALUES
                    (:cid, :pid, :email, :amount, 'TRY', 'webhook', :oid, 'completed', :meta)
            """), {
                "cid": content_id,
                "pid": product_id,
                "email": email,
                "amount": amount,
                "oid": order_id,
                "meta": json.dumps({"title": product_title}),
            })
            db.commit()

            if email:
                db.execute(sa_text("""
                    INSERT INTO email_leads (email, source, page)
                    VALUES (:email, 'shopier_purchase', :content)
                    ON CONFLICT (email) DO NOTHING
                """), {"email": email, "content": content_id})
                db.commit()

    return {"received": True}


def _resolve_content_id(title: str, product_id: str) -> str:
    """Map Shopier product title/id to our content_id."""
    t = (title or "").lower()
    if "rol" in t or "matrix" in t:
        return "role_unlock"
    if "ilişki" in t or "iliski" in t:
        return "iliski_acilimi"
    if "para" in t:
        return "para_akisi"
    if "kariyer" in t:
        return "kariyer_acilimi"
    if "haftalık" in t or "haftalik" in t:
        return "haftalik_akis"
    if "sağlık" in t or "enerji" in t or "saglik" in t:
        return "saglik_enerji"
    if "112" in t or "tanrıça" in t:
        return "kitap_112"
    if "ikra" in t:
        return "matrix_code"
    if "kod eğit" in t or "kod egit" in t:
        return "kod_egitmeni"
    if "okuma" in t and "devam" in t:
        return "okuma_devami"
    if "an_kod" in t or "anın kod" in t:
        return "ankod"
    if "bilinçaltı" in t or "bilincalti" in t:
        return "bilinc_alti"
    return product_id or "unknown"


# ═══════════════════════════════════════════════════════════════
# POST /shopier/record — Frontend records a purchase
# ═══════════════════════════════════════════════════════════════

class RecordPurchaseBody(BaseModel):
    content_id: str
    product_id: Optional[str] = None
    device_fp: Optional[str] = None
    amount: Optional[float] = None

@router.post("/record")
def record_purchase(
    body: RecordPurchaseBody,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        try:
            from app.services.auth import decode_token
            payload = decode_token(authorization.replace("Bearer ", "").strip())
            if payload and payload.get("sub"):
                user_id = int(payload["sub"])
        except Exception:
            pass

    existing = db.execute(sa_text("""
        SELECT id FROM shopier_purchases
        WHERE content_id = :cid
          AND (device_fp = :fp OR (user_id IS NOT NULL AND user_id = :uid))
          AND status = 'completed'
        LIMIT 1
    """), {"cid": body.content_id, "fp": body.device_fp or "", "uid": user_id or 0}).first()

    if existing:
        return {"ok": True, "action": "already_recorded"}

    db.execute(sa_text("""
        INSERT INTO shopier_purchases
            (content_id, product_id, device_fp, user_id, amount, source, status)
        VALUES
            (:cid, :pid, :fp, :uid, :amount, 'frontend', 'completed')
    """), {
        "cid": body.content_id,
        "pid": body.product_id or "",
        "fp": body.device_fp or "",
        "uid": user_id,
        "amount": body.amount or 0,
    })
    db.commit()
    return {"ok": True, "action": "recorded"}


# ═══════════════════════════════════════════════════════════════
# GET /shopier/check — Check if content is unlocked
# ═══════════════════════════════════════════════════════════════

@router.get("/check/{content_id}")
def check_purchase(
    content_id: str,
    device_fp: str = "",
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        try:
            from app.services.auth import decode_token
            payload = decode_token(authorization.replace("Bearer ", "").strip())
            if payload and payload.get("sub"):
                user_id = int(payload["sub"])
        except Exception:
            pass

    conditions = []
    params = {"cid": content_id}

    if device_fp:
        conditions.append("device_fp = :fp")
        params["fp"] = device_fp
    if user_id:
        conditions.append("user_id = :uid")
        params["uid"] = user_id

    if not conditions:
        return {"unlocked": False}

    where = " OR ".join(conditions)
    row = db.execute(sa_text(f"""
        SELECT id, created_at FROM shopier_purchases
        WHERE content_id = :cid AND ({where}) AND status = 'completed'
        ORDER BY created_at DESC LIMIT 1
    """), params).first()

    return {"unlocked": bool(row), "purchased_at": str(row[1]) if row else None}


# ═══════════════════════════════════════════════════════════════
# GET /shopier/my-purchases — List all purchases for device/user
# ═══════════════════════════════════════════════════════════════

@router.get("/my-purchases")
def my_purchases(
    device_fp: str = "",
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        try:
            from app.services.auth import decode_token
            payload = decode_token(authorization.replace("Bearer ", "").strip())
            if payload and payload.get("sub"):
                user_id = int(payload["sub"])
        except Exception:
            pass

    conditions = []
    params = {}
    if device_fp:
        conditions.append("device_fp = :fp")
        params["fp"] = device_fp
    if user_id:
        conditions.append("user_id = :uid")
        params["uid"] = user_id

    if not conditions:
        return {"purchases": []}

    where = " OR ".join(conditions)
    rows = db.execute(sa_text(f"""
        SELECT content_id, product_id, amount, created_at
        FROM shopier_purchases
        WHERE ({where}) AND status = 'completed'
        ORDER BY created_at DESC
    """), params).mappings().all()

    return {
        "purchases": [
            {
                "content_id": r["content_id"],
                "product_id": r["product_id"],
                "amount": float(r["amount"]) if r["amount"] else 0,
                "purchased_at": str(r["created_at"]),
            }
            for r in rows
        ]
    }


# ═══════════════════════════════════════════════════════════════
# POST /shopier/collect-email — Email lead collection
# ═══════════════════════════════════════════════════════════════

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

    db.execute(sa_text("""
        INSERT INTO email_leads (email, name, source, page, ip_hash, device_fp, user_id)
        VALUES (:email, :name, :source, :page, :ip, :fp, :uid)
        ON CONFLICT (email) DO UPDATE SET
            name = COALESCE(EXCLUDED.name, email_leads.name),
            source = EXCLUDED.source,
            page = EXCLUDED.page
    """), {
        "email": body.email.strip().lower(),
        "name": body.name,
        "source": body.source,
        "page": body.page,
        "ip": ip_hash,
        "fp": body.device_fp,
        "uid": user_id,
    })
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════
# GET /shopier/admin/purchases — Admin view
# ═══════════════════════════════════════════════════════════════

@router.get("/admin/purchases")
def admin_purchases(
    x_admin_secret: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Admin access denied")

    rows = db.execute(sa_text("""
        SELECT id, content_id, product_id, device_fp, user_id, email,
               amount, source, shopier_order_id, status, created_at
        FROM shopier_purchases ORDER BY created_at DESC LIMIT 100
    """)).mappings().all()

    total = db.execute(sa_text(
        "SELECT COALESCE(SUM(amount), 0) FROM shopier_purchases WHERE status = 'completed'"
    )).scalar()

    leads = db.execute(sa_text(
        "SELECT COUNT(*) FROM email_leads"
    )).scalar()

    return {
        "total_revenue": float(total),
        "total_purchases": len(rows),
        "total_email_leads": leads,
        "purchases": [dict(r) for r in rows],
    }
