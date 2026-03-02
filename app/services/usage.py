# app/services/usage.py
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.usage import Usage
from app.models.user import User

LIMITS = {
    "free": 200,
    "premium": 74,
    "elite": 10**9,   # effectively unlimited
}

def utc_today():
    return datetime.now(timezone.utc).date()

def get_or_create_user(db: Session, external_id: str) -> User:
    u = db.query(User).filter(User.external_id == external_id).first()
    if u:
        return u
    u = User(external_id=external_id, role="free")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

def check_and_increment(db: Session, external_id: str) -> dict:
    """
    Returns:
      { ok: bool, role: str, used: int, limit: int }
    """
    u = get_or_create_user(db, external_id)
    role = (u.role or "free").strip().lower()
    if role not in LIMITS:
        role = "free"

    day = utc_today()
    row = db.query(Usage).filter(Usage.external_id == external_id, Usage.day == day).first()
    if not row:
        row = Usage(external_id=external_id, day=day, total=0)
        db.add(row)
        db.commit()
        db.refresh(row)

    limit = LIMITS[role]
    used = int(row.total or 0)

    if used >= limit:
        return {"ok": False, "role": role, "used": used, "limit": limit}

    row.total = used + 1
    db.add(row)
    db.commit()

    return {"ok": True, "role": role, "used": used + 1, "limit": limit}