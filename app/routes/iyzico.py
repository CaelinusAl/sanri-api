"""
iyzico Checkout Form — init, callback, admin.

Env vars:
  IYZICO_API_KEY         iyzico API key
  IYZICO_SECRET_KEY      iyzico secret key
  IYZICO_BASE_URL        sandbox-api.iyzipay.com  or  api.iyzipay.com
  FRONTEND_URL           Success/cancel redirect base
  SANRI_ADMIN_SECRET     Admin header auth
"""

import os
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import iyzipay
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db import get_db
from app.services.auth import decode_token
from app.models.billing import Purchase, ContentUnlock, UserEntitlement
from app.models.user import User
from app.services.entitlements import (
    grant_entitlement,
    check_access,
    grant_content_unlock,
)

logger = logging.getLogger("iyzico")

router = APIRouter(prefix="/billing/iyzico", tags=["iyzico"])

IYZICO_OPTIONS = {
    "api_key": os.getenv("IYZICO_API_KEY", ""),
    "secret_key": os.getenv("IYZICO_SECRET_KEY", ""),
    "base_url": os.getenv("IYZICO_BASE_URL", "sandbox-api.iyzipay.com"),
}

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
ADMIN_SECRET = os.getenv("SANRI_ADMIN_SECRET", "")

PRODUCT_MAP = {
    "single_read_unlock": {
        "amount": "9.90",
        "content_type": "okuma",
        "label": "Tek Okuma Açma",
    },
    "single_book_unlock": {
        "amount": "14.90",
        "content_type": "book",
        "label": "Tek Kitap Açma",
    },
    "single_book_unlock_112": {
        "amount": "369.00",
        "content_type": "book",
        "label": "112. Kitap: Kendini Yaratan Tanrıça",
    },
    "single_book_unlock_matrix": {
        "amount": "470.00",
        "content_type": "book",
        "label": "Matrix Code: İkra",
    },
    "single_ritual_unlock": {
        "amount": "4.90",
        "content_type": "ritual",
        "label": "Tek Ritüel Açma",
    },
    "weekly_pass": {
        "amount": "29.90",
        "content_type": None,
        "label": "Haftalık Geçiş",
    },
    "premium_monthly": {
        "amount": "79.90",
        "content_type": None,
        "label": "Premium Aylık",
    },
    "premium_yearly": {
        "amount": "599.90",
        "content_type": None,
        "label": "Premium Yıllık",
    },
}

BOOK_PRICE_OVERRIDES = {
    "kitap_112": "369.00",
    "matrix_code": "470.00",
}


# ═══════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════

def _get_current_user_id(authorization: Optional[str] = Header(default=None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    payload = decode_token(authorization.replace("Bearer ", "").strip())
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token")
    return int(payload["sub"])


def _verify_admin(x_admin_secret: Optional[str] = Header(default=None)):
    if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Admin access denied")


# ═══════════════════════════════════════════════════════════════
# POST /billing/iyzico/init — Start iyzico checkout
# ═══════════════════════════════════════════════════════════════

class IyzicoInitRequest(BaseModel):
    product_key: str
    content_id: Optional[str] = None

class IyzicoInitResponse(BaseModel):
    checkout_url: str
    token: str
    status: str

@router.post("/init", response_model=IyzicoInitResponse)
def iyzico_init(
    body: IyzicoInitRequest,
    user_id: int = Depends(_get_current_user_id),
    db: Session = Depends(get_db),
):
    product = PRODUCT_MAP.get(body.product_key)
    if not product:
        raise HTTPException(status_code=400, detail=f"Unknown product: {body.product_key}")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    price = product["amount"]
    if body.product_key == "single_book_unlock" and body.content_id:
        price = BOOK_PRICE_OVERRIDES.get(body.content_id, price)

    conversation_id = f"sanri_{user_id}_{uuid.uuid4().hex[:12]}"
    basket_id = f"B_{user_id}_{uuid.uuid4().hex[:8]}"

    callback_url = f"{FRONTEND_URL}/payment/iyzico-callback"

    buyer_name = (user.display_name or user.email.split("@")[0] or "Kullanici").split()
    first_name = buyer_name[0] if buyer_name else "Kullanici"
    last_name = buyer_name[1] if len(buyer_name) > 1 else "."

    request_data = {
        "locale": "tr",
        "conversationId": conversation_id,
        "price": price,
        "paidPrice": price,
        "currency": "TRY",
        "basketId": basket_id,
        "paymentGroup": "PRODUCT",
        "callbackUrl": callback_url,
        "buyer": {
            "id": str(user_id),
            "name": first_name,
            "surname": last_name,
            "gsmNumber": user.phone or "+905000000000",
            "email": user.email,
            "identityNumber": "11111111111",
            "registrationAddress": "Turkiye",
            "city": "Istanbul",
            "country": "Turkey",
            "zipCode": "34000",
        },
        "billingAddress": {
            "contactName": f"{first_name} {last_name}",
            "city": "Istanbul",
            "country": "Turkey",
            "address": "Turkiye",
            "zipCode": "34000",
        },
        "shippingAddress": {
            "contactName": f"{first_name} {last_name}",
            "city": "Istanbul",
            "country": "Turkey",
            "address": "Turkiye",
            "zipCode": "34000",
        },
        "basketItems": [
            {
                "id": body.product_key,
                "name": product["label"],
                "category1": "Digital Content",
                "itemType": "VIRTUAL",
                "price": price,
            }
        ],
    }

    try:
        checkout_form = iyzipay.CheckoutFormInitialize().create(request_data, IYZICO_OPTIONS)
        result = json.loads(checkout_form.read().decode("utf-8"))
    except Exception as e:
        logger.exception(f"iyzico init error: {e}")
        raise HTTPException(status_code=502, detail="iyzico connection failed")

    if result.get("status") != "success":
        error_msg = result.get("errorMessage", "Unknown error")
        logger.error(f"iyzico init failed: {error_msg}")
        raise HTTPException(status_code=400, detail=f"iyzico error: {error_msg}")

    token = result.get("token", "")
    payment_page_url = result.get("paymentPageUrl", "")

    purchase = Purchase(
        user_id=user_id,
        stripe_customer_id=None,
        stripe_session_id=token,
        stripe_payment_intent_id=None,
        product_key=body.product_key,
        content_id=body.content_id,
        amount=float(price),
        currency="try",
        status="pending",
    )
    db.add(purchase)
    db.commit()

    return IyzicoInitResponse(
        checkout_url=payment_page_url,
        token=token,
        status="success",
    )


# ═══════════════════════════════════════════════════════════════
# POST /billing/iyzico/callback — iyzico redirects here
# ═══════════════════════════════════════════════════════════════

@router.post("/callback")
async def iyzico_callback(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    token = form.get("token", "")

    if not token:
        logger.warning("iyzico callback: no token")
        return RedirectResponse(url=f"{FRONTEND_URL}/payment/cancel?reason=no_token", status_code=303)

    try:
        retrieve_request = {"locale": "tr", "token": token}
        result_raw = iyzipay.CheckoutForm().retrieve(retrieve_request, IYZICO_OPTIONS)
        result = json.loads(result_raw.read().decode("utf-8"))
    except Exception as e:
        logger.exception(f"iyzico retrieve error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/payment/cancel?reason=retrieve_error", status_code=303)

    payment_status = result.get("paymentStatus")
    iyzico_status = result.get("status")
    payment_id = result.get("paymentId", "")
    fraud_status = result.get("fraudStatus")

    logger.info(f"iyzico callback: status={iyzico_status} paymentStatus={payment_status} fraud={fraud_status} id={payment_id}")

    purchase = db.query(Purchase).filter(Purchase.stripe_session_id == token).first()

    if iyzico_status == "success" and payment_status == "SUCCESS" and fraud_status == 1:
        if purchase:
            purchase.status = "completed"
            purchase.stripe_payment_intent_id = payment_id
            db.commit()

            _grant_iyzico_entitlement(purchase, db)

        return RedirectResponse(
            url=f"{FRONTEND_URL}/payment/success?session_id={token}&provider=iyzico",
            status_code=303,
        )
    else:
        error_msg = result.get("errorMessage", "payment_failed")
        if purchase:
            purchase.status = "failed"
            purchase.failure_reason = error_msg
            db.commit()

        return RedirectResponse(
            url=f"{FRONTEND_URL}/payment/cancel?reason={error_msg}",
            status_code=303,
        )


def _grant_iyzico_entitlement(purchase: Purchase, db: Session):
    """Grant entitlements after successful iyzico payment."""
    user_id = purchase.user_id
    product_key = purchase.product_key
    content_id = purchase.content_id

    product = PRODUCT_MAP.get(product_key, {})

    if product_key == "weekly_pass":
        grant_entitlement(
            db, user_id, product_key,
            source="iyzico",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            purchase_id=purchase.id,
        )
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_premium = True
            user.premium_until = datetime.now(timezone.utc) + timedelta(days=7)
            user.premium_source = "iyzico_weekly"
            user.plan = "weekly"
            db.commit()

    elif product_key in ("premium_monthly", "premium_yearly"):
        days = 365 if product_key == "premium_yearly" else 30
        expires = datetime.now(timezone.utc) + timedelta(days=days)

        grant_entitlement(
            db, user_id, product_key,
            source="iyzico",
            expires_at=expires,
            purchase_id=purchase.id,
        )
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_premium = True
            user.premium_until = expires
            user.premium_source = "iyzico"
            user.plan = "premium"
            db.commit()

    elif content_id and product.get("content_type"):
        grant_content_unlock(
            db, user_id, content_id, product_key,
            purchase_id=purchase.id,
        )


# ═══════════════════════════════════════════════════════════════
# GET /billing/iyzico/status — Check payment by token
# ═══════════════════════════════════════════════════════════════

@router.get("/status")
def iyzico_payment_status(
    token: str = Query(...),
    user_id: int = Depends(_get_current_user_id),
    db: Session = Depends(get_db),
):
    purchase = db.query(Purchase).filter(
        Purchase.stripe_session_id == token,
        Purchase.user_id == user_id,
    ).first()

    if not purchase:
        raise HTTPException(status_code=404, detail="Payment not found")

    return {
        "status": purchase.status,
        "product_key": purchase.product_key,
        "content_id": purchase.content_id,
        "amount": purchase.amount,
        "created_at": purchase.created_at.isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# ADMIN: GET /billing/iyzico/admin/payments
# ═══════════════════════════════════════════════════════════════

@router.get("/admin/payments")
def admin_iyzico_payments(
    _: None = Depends(_verify_admin),
    db: Session = Depends(get_db),
):
    total_revenue = (
        db.query(func.sum(Purchase.amount))
        .filter(Purchase.status == "completed")
        .scalar() or 0
    )
    total_purchases = db.query(func.count(Purchase.id)).filter(Purchase.status == "completed").scalar() or 0
    failed_purchases = db.query(func.count(Purchase.id)).filter(Purchase.status == "failed").scalar() or 0

    recent = (
        db.query(Purchase)
        .order_by(Purchase.created_at.desc())
        .limit(50)
        .all()
    )

    return {
        "summary": {
            "total_revenue": round(total_revenue, 2),
            "total_purchases": total_purchases,
            "failed_purchases": failed_purchases,
        },
        "payments": [
            {
                "id": p.id,
                "user_id": p.user_id,
                "product_key": p.product_key,
                "content_id": p.content_id,
                "amount": p.amount,
                "currency": p.currency,
                "status": p.status,
                "failure_reason": p.failure_reason,
                "created_at": p.created_at.isoformat(),
            }
            for p in recent
        ],
    }
