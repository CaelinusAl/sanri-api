from datetime import datetime, timedelta
from fastapi import HTTPException

def require_premium(user) -> None:
    if not getattr(user, "is_premium", False):
        raise HTTPException(status_code=403, detail="SANRI INNER CIRCLE gerekli")

def require_30_days(user) -> None:
    last = getattr(user, "last_matrix_deep_analysis", None)
    if not last:
        return
    next_allowed = last + timedelta(days=30)
    now = datetime.utcnow()
    if now < next_allowed:
        days_left = max(0, (next_allowed - now).days)
        raise HTTPException(status_code=403, detail=f"Derin analiz 30 günde 1. Days left: {days_left}")

def enforce_self_only(user, name: str, birth_date: str) -> None:
    # Kullanıcı daha önce kilitlendiyse sadece kendisi
    if getattr(user, "name", None) and getattr(user, "birth_date", None):
        if user.name.strip().lower() != name.strip().lower() or user.birth_date.strip() != birth_date.strip():
            raise HTTPException(status_code=403, detail="Sadece kendi profilin için kullanılabilir")