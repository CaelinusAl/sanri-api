from datetime import datetime, timedelta
from fastapi import HTTPException

def ensure_premium(user) -> None:
    if not user.is_premium:
        raise HTTPException(status_code=403, detail="Premium gerekli")

def ensure_self_only(user, name: str, birth_date: str) -> None:
    # ilk kullanımda user profiline kilitle
    if not user.name and not user.birth_date:
        return
    if (user.name or "").strip().lower() != (name or "").strip().lower():
        raise HTTPException(status_code=403, detail="Sadece kendi profilin için kullanılabilir")
    if (user.birth_date or "").strip() != (birth_date or "").strip():
        raise HTTPException(status_code=403, detail="Sadece kendi profilin için kullanılabilir")

def ensure_30_days(user) -> None:
    last = user.last_matrix_deep_analysis
    if not last:
        return
    next_allowed = last + timedelta(days=30)
    now = datetime.utcnow()
    if now < next_allowed:
        days_left = max(0, (next_allowed - now).days)
        raise HTTPException(status_code=403, detail=f"Derin analiz 30 günde 1. Days left: {days_left}")