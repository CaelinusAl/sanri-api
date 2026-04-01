"""
Stripe Billing — checkout, webhooks, access, sync, admin.

Env vars:
  STRIPE_SECRET_KEY          Stripe API secret
  STRIPE_WEBHOOK_SECRET      Webhook endpoint secret
  STRIPE_PUBLISHABLE_KEY     For frontend config
  FRONTEND_URL               Success/cancel redirect base
  SANRI_ADMIN_SECRET         Admin header auth
  STRIPE_PRICE_*             Per-product price IDs
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db import get_db
from app.services.auth import decode_token
from app.models.billing import Subscription, Purchase, ContentUnlock, UserEntitlement
from app.models.user import User
from app.services.entitlements import (
    grant_entitlement,
    revoke_subscription_entitlements,
    check_access,
    grant_content_unlock,
    sync_external_entitlements,
)

logger = logging.getLogger("billing")

router = APIRouter(prefix="/billing", tags=["billing"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
ADMIN_SECRET = os.getenv("SANRI_ADMIN_SECRET", "")

PRODUCT_MAP = {
    "single_read_unlock": {
        "mode": "payment",
        "price_env": "STRIPE_PRICE_SINGLE_READ",
        "amount": 990,
        "content_type": "okuma",
    },
    "single_book_unlock": {
        "mode": "payment",
        "price_env": "STRIPE_PRICE_SINGLE_BOOK",
        "amount": 1490,
        "content_type": "book",
    },
    "single_ritual_unlock": {
        "mode": "payment",
        "price_env": "STRIPE_PRICE_SINGLE_RITUAL",
        "amount": 490,
        "content_type": "ritual",
    },
    "weekly_pass": {
        "mode": "payment",
        "price_env": "STRIPE_PRICE_WEEKLY_PASS",
        "amount": 2990,
        "content_type": None,
    },
    "premium_monthly": {
        "mode": "subscription",
        "price_env": "STRIPE_PRICE_PREMIUM_MONTHLY",
        "amount": 7990,
        "content_type": None,
    },
    "premium_yearly": {
        "mode": "subscription",
        "price_env": "STRIPE_PRICE_PREMIUM_YEARLY",
        "amount": 59990,
        "content_type": None,
    },
}


# ═══════════════════════════════════════════════════════════════
# AUTH HELPERS
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


def _get_or_create_stripe_customer(user_id: int, db: Session) -> str:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.stripe_customer_id:
        return user.stripe_customer_id

    existing_sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
    if existing_sub:
        user.stripe_customer_id = existing_sub.stripe_customer_id
        db.commit()
        return existing_sub.stripe_customer_id

    customer = stripe.Customer.create(
        email=user.email,
        metadata={"sanri_user_id": str(user_id)},
    )
    user.stripe_customer_id = customer.id
    db.commit()
    return customer.id


# ═══════════════════════════════════════════════════════════════
# POST /billing/checkout-session
# ═══════════════════════════════════════════════════════════════

class CheckoutRequest(BaseModel):
    product_key: str
    content_id: Optional[str] = None

class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str

@router.post("/checkout-session", response_model=CheckoutResponse)
def create_checkout_session(
    body: CheckoutRequest,
    user_id: int = Depends(_get_current_user_id),
    db: Session = Depends(get_db),
):
    product = PRODUCT_MAP.get(body.product_key)
    if not product:
        raise HTTPException(status_code=400, detail=f"Unknown product: {body.product_key}")

    price_id = os.getenv(product["price_env"], "")
    if not price_id:
        raise HTTPException(status_code=500, detail=f"Price not configured: {body.product_key}")

    customer_id = _get_or_create_stripe_customer(user_id, db)
    mode = product["mode"]

    metadata = {
        "sanri_user_id": str(user_id),
        "product_key": body.product_key,
    }
    if body.content_id:
        metadata["content_id"] = body.content_id

    success_url = f"{FRONTEND_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{FRONTEND_URL}/payment/cancel"

    params = {
        "customer": customer_id,
        "mode": mode,
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": metadata,
        "locale": "tr",
        "payment_intent_data": {"metadata": metadata} if mode == "payment" else None,
    }
    if mode == "subscription":
        params.pop("payment_intent_data", None)
        params["subscription_data"] = {"metadata": metadata}

    session = stripe.checkout.Session.create(**{k: v for k, v in params.items() if v is not None})

    if mode == "payment":
        purchase = Purchase(
            user_id=user_id,
            stripe_customer_id=customer_id,
            stripe_session_id=session.id,
            product_key=body.product_key,
            content_id=body.content_id,
            amount=product["amount"] / 100,
            currency="try",
            status="pending",
        )
        db.add(purchase)
        db.commit()

    return CheckoutResponse(checkout_url=session.url, session_id=session.id)


# ═══════════════════════════════════════════════════════════════
# POST /billing/webhook
# ═══════════════════════════════════════════════════════════════

@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=400, detail="Bad payload")

    etype = event["type"]
    obj = event["data"]["object"]
    logger.info(f"Stripe webhook: {etype} — {obj.get('id', '?')}")

    handlers = {
        "checkout.session.completed": _on_checkout_completed,
        "customer.subscription.created": _on_subscription_created,
        "customer.subscription.updated": _on_subscription_updated,
        "customer.subscription.deleted": _on_subscription_deleted,
        "invoice.paid": _on_invoice_paid,
        "invoice.payment_failed": _on_invoice_failed,
    }
    handler = handlers.get(etype)
    if handler:
        try:
            handler(obj, db)
        except Exception as e:
            logger.exception(f"Webhook handler error for {etype}: {e}")

    return {"received": True}


def _resolve_user_id(metadata: dict) -> int:
    uid = metadata.get("sanri_user_id", "0")
    return int(uid) if uid else 0


# ── checkout.session.completed ────────────────────────────────

def _on_checkout_completed(session: dict, db: Session):
    meta = session.get("metadata", {})
    user_id = _resolve_user_id(meta)
    product_key = meta.get("product_key", "")
    content_id = meta.get("content_id")

    if not user_id:
        logger.warning("checkout.session.completed: no sanri_user_id")
        return

    mode = session.get("mode")

    if mode == "payment":
        purchase = db.query(Purchase).filter(Purchase.stripe_session_id == session["id"]).first()
        if purchase:
            purchase.status = "completed"
            purchase.stripe_payment_intent_id = session.get("payment_intent")
            db.commit()

        product = PRODUCT_MAP.get(product_key, {})

        if product_key == "weekly_pass":
            grant_entitlement(
                db, user_id, product_key,
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                purchase_id=purchase.id if purchase else None,
            )
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.is_premium = True
                user.premium_until = datetime.now(timezone.utc) + timedelta(days=7)
                user.premium_source = "stripe_weekly"
                user.plan = "weekly"
                db.commit()

        elif content_id and product.get("content_type"):
            grant_content_unlock(
                db, user_id, content_id, product_key,
                purchase_id=purchase.id if purchase else None,
            )

    elif mode == "subscription":
        stripe_sub_id = session.get("subscription")
        if stripe_sub_id:
            _ensure_subscription_record(user_id, session, stripe_sub_id, product_key, db)
            _grant_premium_entitlement(user_id, product_key, stripe_sub_id, db)


# ── customer.subscription.created ─────────────────────────────

def _on_subscription_created(stripe_sub: dict, db: Session):
    meta = stripe_sub.get("metadata", {})
    user_id = _resolve_user_id(meta)
    product_key = meta.get("product_key", "premium_monthly")

    if not user_id:
        return

    _ensure_subscription_record_from_sub(user_id, stripe_sub, product_key, db)
    _grant_premium_entitlement(user_id, product_key, stripe_sub["id"], db)


# ── customer.subscription.updated ─────────────────────────────

def _on_subscription_updated(stripe_sub: dict, db: Session):
    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_sub["id"]
    ).first()
    if not sub:
        return

    sub.status = stripe_sub.get("status", sub.status)
    sub.cancel_at_period_end = stripe_sub.get("cancel_at_period_end", False)

    period_end = stripe_sub.get("current_period_end")
    if period_end:
        sub.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
    period_start = stripe_sub.get("current_period_start")
    if period_start:
        sub.current_period_start = datetime.fromtimestamp(period_start, tz=timezone.utc)

    if stripe_sub.get("canceled_at"):
        sub.canceled_at = datetime.fromtimestamp(stripe_sub["canceled_at"], tz=timezone.utc)

    db.commit()

    if sub.status in ("active", "trialing"):
        _grant_premium_entitlement(
            sub.user_id, sub.product_key, sub.stripe_subscription_id, db,
            expires_at=sub.current_period_end,
        )
    elif sub.status in ("past_due", "unpaid", "canceled"):
        revoke_subscription_entitlements(db, sub.user_id, sub.stripe_subscription_id)


# ── customer.subscription.deleted ─────────────────────────────

def _on_subscription_deleted(stripe_sub: dict, db: Session):
    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_sub["id"]
    ).first()
    if not sub:
        return

    sub.status = "canceled"
    sub.canceled_at = datetime.now(timezone.utc)
    db.commit()

    revoke_subscription_entitlements(db, sub.user_id, sub.stripe_subscription_id)


# ── invoice.paid ──────────────────────────────────────────────

def _on_invoice_paid(invoice: dict, db: Session):
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return

    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_sub_id
    ).first()
    if not sub:
        return

    sub.status = "active"
    sub.failure_reason = None

    stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)
    period_end = stripe_sub.get("current_period_end")
    if period_end:
        sub.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
        sub.current_period_start = datetime.fromtimestamp(
            stripe_sub.get("current_period_start", 0), tz=timezone.utc
        )

    db.commit()

    expires = sub.current_period_end
    _grant_premium_entitlement(sub.user_id, sub.product_key, stripe_sub_id, db, expires_at=expires)

    user = db.query(User).filter(User.id == sub.user_id).first()
    if user:
        user.is_premium = True
        user.premium_until = expires
        db.commit()


# ── invoice.payment_failed ────────────────────────────────────

def _on_invoice_failed(invoice: dict, db: Session):
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return

    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_sub_id
    ).first()
    if not sub:
        return

    sub.failure_reason = (
        invoice.get("last_payment_error", {}).get("message")
        or "payment_failed"
    )
    db.commit()


# ── Subscription record helpers ───────────────────────────────

def _ensure_subscription_record(
    user_id: int, session: dict, stripe_sub_id: str, product_key: str, db: Session,
):
    existing = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_sub_id
    ).first()
    if existing:
        return existing

    stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)
    return _ensure_subscription_record_from_sub(user_id, stripe_sub, product_key, db)


def _ensure_subscription_record_from_sub(
    user_id: int, stripe_sub: dict, product_key: str, db: Session,
) -> Subscription:
    existing = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_sub["id"]
    ).first()
    if existing:
        return existing

    period_start = stripe_sub.get("current_period_start")
    period_end = stripe_sub.get("current_period_end")

    price_id = ""
    items = stripe_sub.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")

    sub = Subscription(
        user_id=user_id,
        stripe_customer_id=stripe_sub.get("customer", ""),
        stripe_subscription_id=stripe_sub["id"],
        stripe_price_id=price_id,
        product_key=product_key,
        status=stripe_sub.get("status", "active"),
        current_period_start=datetime.fromtimestamp(period_start, tz=timezone.utc) if period_start else None,
        current_period_end=datetime.fromtimestamp(period_end, tz=timezone.utc) if period_end else None,
    )
    db.add(sub)
    db.commit()
    return sub


def _grant_premium_entitlement(
    user_id: int, product_key: str, stripe_sub_id: str, db: Session,
    expires_at: Optional[datetime] = None,
):
    if not expires_at:
        if product_key == "premium_yearly":
            expires_at = datetime.now(timezone.utc) + timedelta(days=365)
        else:
            expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    grant_entitlement(
        db, user_id, product_key,
        stripe_subscription_id=stripe_sub_id,
        expires_at=expires_at,
    )

    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_premium = True
        user.premium_source = "stripe"
        user.plan = "premium"
        user.premium_until = expires_at
        db.commit()


# ═══════════════════════════════════════════════════════════════
# POST /billing/free-unlock — one-time free content unlock
# ═══════════════════════════════════════════════════════════════

class FreeUnlockRequest(BaseModel):
    content_id: str
    content_type: str = "okuma"

@router.post("/free-unlock")
def use_free_unlock(
    body: FreeUnlockRequest,
    user_id: int = Depends(_get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.free_unlock_used:
        raise HTTPException(status_code=409, detail="Free unlock already used")

    product_key_map = {
        "okuma": "single_read_unlock",
        "book": "single_book_unlock",
        "ritual": "single_ritual_unlock",
    }
    product_key = product_key_map.get(body.content_type, "single_read_unlock")

    grant_content_unlock(db, user_id, body.content_id, product_key)

    user.free_unlock_used = True
    db.commit()

    return {
        "success": True,
        "content_id": body.content_id,
        "message": "Free unlock granted",
    }


# ═══════════════════════════════════════════════════════════════
# GET /billing/me/access — SINGLE SOURCE OF TRUTH
# ═══════════════════════════════════════════════════════════════

@router.get("/me/access")
def get_my_access(
    content_id: Optional[str] = Query(default=None),
    user_id: int = Depends(_get_current_user_id),
    db: Session = Depends(get_db),
):
    return check_access(db, user_id, content_id=content_id)


# ═══════════════════════════════════════════════════════════════
# POST /billing/sync-entitlements  (RevenueCat-ready)
# ═══════════════════════════════════════════════════════════════

class EntitlementItem(BaseModel):
    entitlement_key: str
    product_key: Optional[str] = None
    expires_at: Optional[str] = None
    is_active: bool = True

class SyncRequest(BaseModel):
    user_id: int
    source: str = "revenuecat"
    entitlements: List[EntitlementItem]

@router.post("/sync-entitlements")
def sync_entitlements(
    body: SyncRequest,
    _: None = Depends(_verify_admin),
    db: Session = Depends(get_db),
):
    sync_external_entitlements(
        db,
        body.user_id,
        [e.model_dump() for e in body.entitlements],
        source=body.source,
    )
    return {"synced": len(body.entitlements), "user_id": body.user_id}


# ═══════════════════════════════════════════════════════════════
# GET /billing/status  (backward compat, delegates to access)
# ═══════════════════════════════════════════════════════════════

@router.get("/status")
def billing_status(
    user_id: int = Depends(_get_current_user_id),
    db: Session = Depends(get_db),
):
    access = check_access(db, user_id)
    return {
        **access,
        "unlocked_content": [
            {"content_id": cid} for cid in access["unlocked_content_ids"]
        ],
    }


# ═══════════════════════════════════════════════════════════════
# GET /billing/content-access/{content_id}  (backward compat)
# ═══════════════════════════════════════════════════════════════

@router.get("/content-access/{content_id}")
def content_access_check(
    content_id: str,
    user_id: int = Depends(_get_current_user_id),
    db: Session = Depends(get_db),
):
    access = check_access(db, user_id, content_id=content_id)
    return access["content_access"] or {"has_access": False, "reason": "locked"}


# ═══════════════════════════════════════════════════════════════
# GET /billing/config  (public)
# ═══════════════════════════════════════════════════════════════

@router.get("/config")
def billing_config():
    return {
        "publishable_key": os.getenv("STRIPE_PUBLISHABLE_KEY", ""),
        "products": {
            key: {
                "mode": val["mode"],
                "amount": val["amount"],
                "content_type": val["content_type"],
            }
            for key, val in PRODUCT_MAP.items()
        },
    }


# ═══════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.get("/admin/summary")
def admin_summary(
    _: None = Depends(_verify_admin),
    db: Session = Depends(get_db),
):
    total_revenue = db.query(func.sum(Purchase.amount)).filter(Purchase.status == "completed").scalar() or 0
    total_purchases = db.query(func.count(Purchase.id)).filter(Purchase.status == "completed").scalar() or 0
    failed_purchases = db.query(func.count(Purchase.id)).filter(Purchase.status == "failed").scalar() or 0
    active_subs = db.query(func.count(Subscription.id)).filter(
        Subscription.status.in_(["active", "trialing"])
    ).scalar() or 0
    canceled_subs = db.query(func.count(Subscription.id)).filter(
        Subscription.status == "canceled"
    ).scalar() or 0
    total_unlocks = db.query(func.count(ContentUnlock.id)).scalar() or 0
    active_entitlements = db.query(func.count(UserEntitlement.id)).filter(
        UserEntitlement.is_active == True
    ).scalar() or 0

    recent_purchases = (
        db.query(Purchase)
        .order_by(Purchase.created_at.desc())
        .limit(30)
        .all()
    )

    all_subs = (
        db.query(Subscription)
        .order_by(Subscription.created_at.desc())
        .limit(30)
        .all()
    )

    ents = (
        db.query(UserEntitlement)
        .filter(UserEntitlement.is_active == True)
        .order_by(UserEntitlement.granted_at.desc())
        .limit(30)
        .all()
    )

    unlocks = (
        db.query(ContentUnlock)
        .order_by(ContentUnlock.unlocked_at.desc())
        .limit(30)
        .all()
    )

    return {
        "summary": {
            "total_revenue": round(total_revenue, 2),
            "total_purchases": total_purchases,
            "failed_purchases": failed_purchases,
            "active_subscriptions": active_subs,
            "canceled_subscriptions": canceled_subs,
            "total_content_unlocks": total_unlocks,
            "active_entitlements": active_entitlements,
        },
        "recent_purchases": [
            {
                "id": p.id, "user_id": p.user_id,
                "product_key": p.product_key, "content_id": p.content_id,
                "amount": p.amount, "currency": p.currency,
                "status": p.status, "failure_reason": p.failure_reason,
                "created_at": p.created_at.isoformat(),
            }
            for p in recent_purchases
        ],
        "subscriptions": [
            {
                "id": s.id, "user_id": s.user_id,
                "product_key": s.product_key, "status": s.status,
                "current_period_end": s.current_period_end.isoformat() if s.current_period_end else None,
                "cancel_at_period_end": s.cancel_at_period_end,
                "canceled_at": s.canceled_at.isoformat() if s.canceled_at else None,
                "failure_reason": s.failure_reason,
                "created_at": s.created_at.isoformat(),
            }
            for s in all_subs
        ],
        "entitlements": [
            {
                "id": e.id, "user_id": e.user_id,
                "entitlement_key": e.entitlement_key,
                "product_key": e.product_key, "source": e.source,
                "expires_at": e.expires_at.isoformat() if e.expires_at else None,
                "granted_at": e.granted_at.isoformat(),
            }
            for e in ents
        ],
        "content_unlocks": [
            {
                "id": u.id, "user_id": u.user_id,
                "content_id": u.content_id, "content_type": u.content_type,
                "purchase_id": u.purchase_id,
                "unlocked_at": u.unlocked_at.isoformat(),
            }
            for u in unlocks
        ],
    }
