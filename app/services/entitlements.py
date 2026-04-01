"""
Entitlement service — single source of truth for user access.

product_key  →  entitlement_key mapping:
  premium_monthly      →  premium_access
  premium_yearly       →  premium_access
  weekly_pass          →  weekly_access   (expires in 7d)
  single_read_unlock   →  content:okuma:<content_id>
  single_book_unlock   →  content:book:<content_id>
  single_ritual_unlock →  content:ritual:<content_id>

Sources: stripe, revenuecat, admin_grant, promo
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.billing import UserEntitlement, ContentUnlock, Subscription
from app.models.user import User

logger = logging.getLogger("entitlements")

PRODUCT_TO_ENTITLEMENT = {
    "premium_monthly": "premium_access",
    "premium_yearly": "premium_access",
    "weekly_pass": "weekly_access",
    "single_read_unlock": "content:okuma",
    "single_book_unlock": "content:book",
    "single_ritual_unlock": "content:ritual",
}

CONTENT_TYPE_MAP = {
    "single_read_unlock": "okuma",
    "single_book_unlock": "book",
    "single_ritual_unlock": "ritual",
}


def grant_entitlement(
    db: Session,
    user_id: int,
    product_key: str,
    source: str = "stripe",
    content_id: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    stripe_subscription_id: Optional[str] = None,
    purchase_id: Optional[int] = None,
) -> UserEntitlement:
    """Grant an entitlement derived from a product purchase."""
    base_key = PRODUCT_TO_ENTITLEMENT.get(product_key, product_key)

    if content_id and base_key.startswith("content:"):
        ent_key = f"{base_key}:{content_id}"
    else:
        ent_key = base_key

    if product_key == "weekly_pass" and not expires_at:
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    existing = (
        db.query(UserEntitlement)
        .filter(
            UserEntitlement.user_id == user_id,
            UserEntitlement.entitlement_key == ent_key,
            UserEntitlement.is_active == True,
        )
        .first()
    )

    if existing:
        if expires_at and (not existing.expires_at or expires_at > existing.expires_at):
            existing.expires_at = expires_at
        existing.source = source
        if stripe_subscription_id:
            existing.stripe_subscription_id = stripe_subscription_id
        if purchase_id:
            existing.purchase_id = purchase_id
        db.commit()
        db.refresh(existing)
        return existing

    ent = UserEntitlement(
        user_id=user_id,
        entitlement_key=ent_key,
        product_key=product_key,
        source=source,
        is_active=True,
        expires_at=expires_at,
        stripe_subscription_id=stripe_subscription_id,
        purchase_id=purchase_id,
    )
    db.add(ent)
    db.commit()
    db.refresh(ent)

    _sync_user_premium_flag(db, user_id)

    return ent


def revoke_entitlement(
    db: Session,
    user_id: int,
    entitlement_key: str,
    stripe_subscription_id: Optional[str] = None,
):
    """Revoke a specific entitlement."""
    q = db.query(UserEntitlement).filter(
        UserEntitlement.user_id == user_id,
        UserEntitlement.entitlement_key == entitlement_key,
        UserEntitlement.is_active == True,
    )
    if stripe_subscription_id:
        q = q.filter(UserEntitlement.stripe_subscription_id == stripe_subscription_id)

    ents = q.all()
    for ent in ents:
        ent.is_active = False
        ent.revoked_at = datetime.now(timezone.utc)

    db.commit()
    _sync_user_premium_flag(db, user_id)


def revoke_subscription_entitlements(db: Session, user_id: int, stripe_subscription_id: str):
    """Revoke all entitlements tied to a specific subscription."""
    ents = (
        db.query(UserEntitlement)
        .filter(
            UserEntitlement.user_id == user_id,
            UserEntitlement.stripe_subscription_id == stripe_subscription_id,
            UserEntitlement.is_active == True,
        )
        .all()
    )
    now = datetime.now(timezone.utc)
    for ent in ents:
        ent.is_active = False
        ent.revoked_at = now
    db.commit()
    _sync_user_premium_flag(db, user_id)


def check_access(db: Session, user_id: int, content_id: Optional[str] = None) -> dict:
    """
    The single source of truth for user access.
    Returns a full access manifest consumed by the frontend.
    """
    now = datetime.now(timezone.utc)

    user = db.query(User).filter(User.id == user_id).first()
    has_free_unlock = bool(user and not user.free_unlock_used)

    active_ents = (
        db.query(UserEntitlement)
        .filter(
            UserEntitlement.user_id == user_id,
            UserEntitlement.is_active == True,
        )
        .all()
    )

    valid_ents = []
    expired_keys = []
    for e in active_ents:
        if e.expires_at and e.expires_at < now:
            e.is_active = False
            e.revoked_at = now
            expired_keys.append(e.entitlement_key)
        else:
            valid_ents.append(e)

    if expired_keys:
        db.commit()
        _sync_user_premium_flag(db, user_id)

    has_premium = any(e.entitlement_key == "premium_access" for e in valid_ents)
    has_weekly = any(e.entitlement_key == "weekly_access" for e in valid_ents)

    unlocked_content_ids = set()
    for e in valid_ents:
        if e.entitlement_key.startswith("content:"):
            parts = e.entitlement_key.split(":", 2)
            if len(parts) == 3:
                unlocked_content_ids.add(parts[2])

    content_access = None
    if content_id:
        if has_premium or has_weekly:
            content_access = {"has_access": True, "reason": "premium"}
        elif content_id in unlocked_content_ids:
            content_access = {"has_access": True, "reason": "unlocked"}
        else:
            content_access = {"has_access": False, "reason": "locked"}

    active_sub = (
        db.query(Subscription)
        .filter(
            Subscription.user_id == user_id,
            Subscription.status.in_(["active", "trialing"]),
        )
        .order_by(Subscription.created_at.desc())
        .first()
    )

    premium_until = None
    for e in valid_ents:
        if e.entitlement_key in ("premium_access", "weekly_access") and e.expires_at:
            if premium_until is None or e.expires_at > premium_until:
                premium_until = e.expires_at

    return {
        "is_premium": has_premium or has_weekly,
        "plan": "premium" if has_premium else "weekly" if has_weekly else "free",
        "premium_until": premium_until.isoformat() if premium_until else None,
        "has_free_unlock": has_free_unlock,
        "entitlements": [
            {
                "key": e.entitlement_key,
                "product_key": e.product_key,
                "source": e.source,
                "expires_at": e.expires_at.isoformat() if e.expires_at else None,
                "granted_at": e.granted_at.isoformat(),
            }
            for e in valid_ents
        ],
        "unlocked_content_ids": sorted(unlocked_content_ids),
        "subscription": {
            "id": active_sub.stripe_subscription_id,
            "product_key": active_sub.product_key,
            "status": active_sub.status,
            "current_period_end": active_sub.current_period_end.isoformat() if active_sub.current_period_end else None,
            "cancel_at_period_end": active_sub.cancel_at_period_end,
        } if active_sub else None,
        "content_access": content_access,
    }


def sync_external_entitlements(
    db: Session,
    user_id: int,
    entitlements: list[dict],
    source: str = "revenuecat",
):
    """
    Upsert entitlements from an external source (RevenueCat, admin, promo).
    Each item: { entitlement_key, product_key?, expires_at?, is_active }
    """
    now = datetime.now(timezone.utc)

    for item in entitlements:
        ent_key = item["entitlement_key"]
        is_active = item.get("is_active", True)
        expires_str = item.get("expires_at")
        expires_at = datetime.fromisoformat(expires_str) if expires_str else None

        existing = (
            db.query(UserEntitlement)
            .filter(
                UserEntitlement.user_id == user_id,
                UserEntitlement.entitlement_key == ent_key,
                UserEntitlement.source == source,
            )
            .first()
        )

        if existing:
            existing.is_active = is_active
            existing.expires_at = expires_at
            existing.product_key = item.get("product_key", existing.product_key)
            if not is_active and not existing.revoked_at:
                existing.revoked_at = now
        else:
            ent = UserEntitlement(
                user_id=user_id,
                entitlement_key=ent_key,
                product_key=item.get("product_key"),
                source=source,
                is_active=is_active,
                expires_at=expires_at,
            )
            db.add(ent)

    db.commit()
    _sync_user_premium_flag(db, user_id)


def grant_content_unlock(
    db: Session,
    user_id: int,
    content_id: str,
    product_key: str,
    purchase_id: Optional[int] = None,
):
    """Record a content unlock + create the entitlement."""
    content_type = CONTENT_TYPE_MAP.get(product_key, "okuma")

    existing = (
        db.query(ContentUnlock)
        .filter(ContentUnlock.user_id == user_id, ContentUnlock.content_id == content_id)
        .first()
    )
    if not existing:
        unlock = ContentUnlock(
            user_id=user_id,
            content_id=content_id,
            content_type=content_type,
            purchase_id=purchase_id,
        )
        db.add(unlock)
        db.commit()

    grant_entitlement(
        db, user_id, product_key,
        content_id=content_id,
        purchase_id=purchase_id,
    )


def _sync_user_premium_flag(db: Session, user_id: int):
    """Keep User.is_premium in sync with the entitlement table."""
    now = datetime.now(timezone.utc)
    has_premium = (
        db.query(UserEntitlement)
        .filter(
            UserEntitlement.user_id == user_id,
            UserEntitlement.entitlement_key.in_(["premium_access", "weekly_access"]),
            UserEntitlement.is_active == True,
        )
        .first()
    ) is not None

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return

    if user.is_premium != has_premium:
        user.is_premium = has_premium
        if not has_premium:
            user.plan = "free"
            user.premium_source = None
        db.commit()
