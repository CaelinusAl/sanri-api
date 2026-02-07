# app/routes/subscription.py
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/subscription", tags=["subscription"])

@router.get("/plans")
def plans(language: str = Query(default="tr")):
    # Frontend plans bekliyor → 200 dönelim
    return {
        "language": language,
        "plans": [
            {"id": "free", "name": "Free", "price": 0, "currency": "TRY"},
            {"id": "premium", "name": "Premium", "price": 0, "currency": "TRY", "note": "Coming soon"},
        ],
    }

@router.get("/status")
def status(language: str = Query(default="tr")):
    # Frontend status bekliyor → 200 dönelim
    return {
        "language": language,
        "is_premium": False,
        "plan": "free",
        "limits": {"sanri_daily": 3},
        "used": {"sanri_daily": 0},
    }

@router.get("/upgrade-trigger")
def upgrade_trigger():
    # Frontend "day3/day7 prompt" gibi şeyler çekiyor
    return {"should_prompt": False, "reason": None}