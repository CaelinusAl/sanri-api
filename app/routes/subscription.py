import logging
from typing import Optional
from fastapi import APIRouter, Query, Header, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import decode_token
from app.models.user import User
from app.models.billing import Subscription, ContentUnlock

logger = logging.getLogger("subscription")

router = APIRouter(prefix="/api/subscription", tags=["subscription"])


def _try_get_user_id(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = decode_token(authorization.replace("Bearer ", "").strip())
    if not payload or not payload.get("sub"):
        return None
    return int(payload["sub"])


@router.get("/plans")
def plans(language: str = Query(default="tr")):
    tr = language == "tr"
    plans_list = [
        {
            "id": "free",
            "name": "Ücretsiz" if tr else "Free",
            "tier": "free",
            "note": "Günlük sınırlı erişim" if tr else "Limited daily access",
        },
        {
            "id": "premium_monthly",
            "name": "Premium Aylık" if tr else "Premium Monthly",
            "tier": "premium",
            "price": "₺79.90/ay" if tr else "₺79.90/mo",
            "note": "Tüm içeriklere tam erişim" if tr else "Full access to all content",
        },
        {
            "id": "premium_yearly",
            "name": "Premium Yıllık" if tr else "Premium Yearly",
            "tier": "premium",
            "price": "₺599.90/yıl" if tr else "₺599.90/yr",
            "badge": "EN AVANTAJLI" if tr else "BEST VALUE",
            "note": "Tüm içerikler + %37 tasarruf" if tr else "All content + 37% savings",
        },
    ]
    return {"plans": plans_list, "data": plans_list, "items": plans_list, "language": language}


@router.get("/status")
def status(
    language: str = Query(default="tr"),
    user_id: Optional[int] = Depends(_try_get_user_id),
    db: Session = Depends(get_db),
):
    if not user_id:
        return {
            "is_premium": False, "isPremium": False,
            "plan": "free", "currentPlan": "free",
            "limits": {"sanri_daily": 20}, "used": {"sanri_daily": 0},
        }

    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"is_premium": False, "isPremium": False, "plan": "free", "currentPlan": "free"}

        active_sub = (
            db.query(Subscription)
            .filter(Subscription.user_id == user_id, Subscription.status.in_(["active", "trialing"]))
            .order_by(Subscription.created_at.desc())
            .first()
        )

        unlocks_count = db.query(ContentUnlock).filter(ContentUnlock.user_id == user_id).count()

        return {
            "is_premium": user.is_premium,
            "isPremium": user.is_premium,
            "plan": user.plan or "free",
            "currentPlan": user.plan or "free",
            "premium_until": user.premium_until.isoformat() if user.premium_until else None,
            "subscription": {
                "product_key": active_sub.product_key,
                "status": active_sub.status,
                "cancel_at_period_end": active_sub.cancel_at_period_end,
                "current_period_end": active_sub.current_period_end.isoformat() if active_sub.current_period_end else None,
            } if active_sub else None,
            "unlocked_content_count": unlocks_count,
            "limits": {"sanri_daily": 999 if user.is_premium else 20},
            "used": {"sanri_daily": 0},
        }
    except Exception:
        logger.exception("GET /api/subscription/status failed user_id=%s", user_id)
        return {
            "is_premium": False,
            "isPremium": False,
            "plan": "free",
            "currentPlan": "free",
            "limits": {"sanri_daily": 20},
            "used": {"sanri_daily": 0},
            "subscription": None,
        }
