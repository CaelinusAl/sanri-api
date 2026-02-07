# app/routes/subscription.py
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/subscription", tags=["subscription"])

def _plans_payload(language: str):
    plans_list = [
        {"id": "free", "name": "Free", "price": 0, "currency": "TRY"},
        {"id": "premium", "name": "Premium", "price": 0, "currency": "TRY", "note": "Coming soon"},
    ]
    return plans_list

@router.get("/plans")
def plans(language: str = Query(default="tr")):
    plans_list = _plans_payload(language)

    # ✅ Hem array gibi (frontend data.map isterse) hem object gibi (data.plans.map isterse)
    # Bazı frontendler direkt array bekliyor → bunun için response'u list yapıyoruz
    # Ama FastAPI dict döndürür; bu yüzden "plans" key'i ile de veriyoruz.
    return {
        "plans": plans_list,
        "data": plans_list,      # bazı kodlar data.map yapar
        "items": plans_list,     # bazı kodlar items.map yapar
        "language": language,
    }

@router.get("/status")
def status(language: str = Query(default="tr")):
    return {
        "is_premium": False,
        "plan": "free",
        "limits": {"sanri_daily": 3},
        "used": {"sanri_daily": 0},
        "language": language,
        # bazı kodlar status.plan veya status.isPremium bekler:
        "isPremium": False,
        "currentPlan": "free",
    }

@router.get("/upgrade-trigger")
def upgrade_trigger():
    return {"should_prompt": False, "reason": None}