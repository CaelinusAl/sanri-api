from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/subscription", tags=["subscription"])


@router.get("/plans")
def plans(language: str = Query(default="tr")):
    tr = language == "tr"
    plans_list = [
        {
            "id": "free",
            "name": "Free" if not tr else "Ucretsiz",
            "tier": "free",
            "note": "Gunluk sinirli erisim" if tr else "Limited daily access",
        },
        {
            "id": "premium",
            "name": "Premium",
            "tier": "premium",
            "note": "Tam erisim - RevenueCat uzerinden yonetilir" if tr else "Full access - managed via RevenueCat",
        },
    ]

    return {
        "plans": plans_list,
        "data": plans_list,
        "items": plans_list,
        "language": language,
    }


@router.get("/status")
def status(language: str = Query(default="tr")):
    return {
        "is_premium": False,
        "plan": "free",
        "limits": {"sanri_daily": 20},
        "used": {"sanri_daily": 0},
        "language": language,
        "isPremium": False,
        "currentPlan": "free",
        "note": "Premium status is managed by RevenueCat SDK on the client side.",
    }
