from datetime import datetime, timedelta, timezone
from fastapi import HTTPException

# Şimdilik “fake user store” yerine DB bağlamak daha doğru.
# Ama senin User modelin/DB yapın tam net değil diye
# önce minimal bir in-memory yaklaşım + placeholder koyuyorum.

# ✅ TODO: Bunu auth sistemindeki gerçek kullanıcı modelinle değiştir.
# Örn: from app.auth import get_current_user, db session vs.

class SimpleUser:
    def __init__(self, user_id: str, name: str, birth_date: str, is_premium: bool, last_matrix_deep_analysis=None):
        self.user_id = user_id
        self.name = name
        self.birth_date = birth_date
        self.is_premium = is_premium
        self.last_matrix_deep_analysis = last_matrix_deep_analysis

# DEMO STORE (şimdilik)
USERS = {
    # örnek: user_id: SimpleUser(...)
    # "u1": SimpleUser("u1", "SELIN IRMAK", "21.06.1989", True, None),
}

def get_user_or_401(x_user_id: str | None) -> SimpleUser:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-Id")
    u = USERS.get(x_user_id)
    if not u:
        raise HTTPException(status_code=401, detail="Unknown user")
    return u

def enforce_premium_or_403(user: SimpleUser) -> None:
    if not getattr(user, "is_premium", False):
        raise HTTPException(status_code=403, detail="Premium required")

def enforce_self_only_or_403(user: SimpleUser, name: str, birth_date: str) -> None:
    # Basit karşılaştırma (sen normalize edebilirsin)
    if (user.name or "").strip().lower() != (name or "").strip().lower():
        raise HTTPException(status_code=403, detail="Only your own deep analysis is allowed")
    if (user.birth_date or "").strip() != (birth_date or "").strip():
        raise HTTPException(status_code=403, detail="Only your own deep analysis is allowed")

def enforce_30d_rule_or_403(user: SimpleUser) -> None:
    last = getattr(user, "last_matrix_deep_analysis", None)
    if not last:
        return
    now = datetime.now(timezone.utc)
    if last.tzinfo is None:
        # naive ise utc varsay
        last = last.replace(tzinfo=timezone.utc)
    if now - last < timedelta(days=30):
        remaining = timedelta(days=30) - (now - last)
        days_left = max(0, int(remaining.total_seconds() // 86400))
        raise HTTPException(status_code=403, detail=f"Deep analysis available once every 30 days. Days left: {days_left}")

def mark_matrix_deep_used(user: SimpleUser) -> None:
    user.last_matrix_deep_analysis = datetime.now(timezone.utc)